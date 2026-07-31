/**
 * 對講機的狀態與副作用。
 *
 * ⚠️ 為什麼獨立成一個 hook：`app/src/app/elder/talk.tsx` 是 542 行的單一元件，
 * 權限、手勢、連線、播放、續拉佇列全塞在裡面。那份程式碼能動，但每一次改動都
 * 要重讀整支才知道會影響什麼。這裡把「狀態與副作用」與「畫面」切開，畫面只讀值。
 *
 * ⚠️ 依賴全部以 `deps` 注入。那不是為了測試跑得快——對講機的 bug 幾乎都是**時序**
 * 問題（放開比開錄先到、播放中又開口、上一輪的續拉沒作廢），而時序只有在能精確
 * 控制每一步的環境裡才測得出來。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api";
import { strings } from "@/strings";
import { unlockAudio } from "@/talk/audioUnlock";
import {
  createWebPlayer,
  revokeQueuedReplyAudio as revokeQueuedReplyAudioImpl,
  writeReplyAudio,
  type WebPlayer,
} from "@/talk/playback";
import {
  createRecorder,
  probeMicrophone,
  type MicrophoneProbeResult,
  type Recorder,
} from "@/talk/recorder";
import { createTalkGesture } from "@/talk/talkGesture";
import {
  createPlaybackQueue,
  createTalkSocket,
  playAndWait,
  type PlaybackItem,
  type TalkFrame,
} from "@/talk/talkSocket";

import {
  getTurnChunk as getTurnChunkApi,
  postTurn as postTurnApi,
  type ElderPlace,
} from "./api";
import { currentPlace as currentPlaceApi } from "./location";

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

/**
 * 長按門檻（毫秒）。App 靠 `Pressable` 的 `delayLongPress` 預設值，網頁沒有
 * 對應物，自己計時。數值與 App 一致，兩邊的手感才一樣。
 */
const LONG_PRESS_MS = 500;

/**
 * 送出之後最多等多久還沒有任何下行訊框，就放長輩回去重講（毫秒）。
 *
 * ⚠️ **為什麼需要它**：走長連線時，「送出」與「收到回覆」是兩件分開的事——送出
 * 之後這裡就 `return` 了，畫面停在「金孫想一下…」、麥克風鍵停用，等訊框回來才
 * 解除。連線斷在半路（隧道抖一下）或後端那一輪掉了的時候，訊框永遠不會來，
 * 長輩就此**再也按不動任何東西**，畫面上也沒有任何說明。`playAndWait` 與
 * `recorder.stop()` 各自都有保險逾時（Task 4），這是同一條路上最後一個沒有保險
 * 的環節。
 *
 * 數值取自後端自己的兩個上限：排隊逾時 `turn_queue_timeout_seconds`（預設 30 秒）
 * ＋單輪預算 `turn_budget_seconds`（預設 30 秒）＝最壞 60 秒，再留 15 秒緩衝。
 * 寧可長到幾乎不會誤觸發——誤觸發會讓長輩以為失敗而再講一次，反而多吃一輪 GPU。
 * 每收到一則下行訊框就重新起算（見 `onFrame`），排隊中的人不會被自己的保險打斷。
 */
const THINKING_TIMEOUT_MS = 75_000;

/** 分段播放的進度。`digest` 綁定這是哪一輪的回覆——換一輪就整個作廢。 */
type ChunkQueue = {
  digest: string;
  total: number;
  /** 下一個「要去取」的段號（第 0 段已隨回覆拿到）。 */
  nextIndex: number;
  /** 已在背景取的下一段；一邊播這段一邊取下一段，段與段之間才不會空掉。 */
  pending: Promise<{ audio_url: string } | null> | null;
};

export type TalkDeps = {
  createRecorder: () => Recorder;
  createPlayer: () => WebPlayer;
  createSocket: (url: string) => WebSocket;
  postTurn: typeof postTurnApi;
  getTurnChunk: typeof getTurnChunkApi;
  currentPlace: typeof currentPlaceApi;
  probeMicrophone: typeof probeMicrophone;
  /** 回收「造出來了卻還沒播到」的 blob URL（見 `talk/playback.ts`）。 */
  revokeQueuedReplyAudio: typeof revokeQueuedReplyAudioImpl;
};

/**
 * 麥克風拿不到時，每一種成因各給一句長輩能照做的話。
 *
 * ⚠️ 一律講「請到設定開啟」的話，沒有麥克風的桌機、用區網 IP 連進來的組員，都會
 * 去找一個根本不存在的權限開關——與 Task 5／7 對相機做過的擴充是同一件事。
 */
const MIC_PROBLEM_MESSAGES: Record<Exclude<MicrophoneProbeResult, "granted">, string> = {
  denied: strings.talk.micPermission,
  "not-found": strings.talk.micNotFound,
  "in-use": strings.talk.micInUse,
  "insecure-origin": strings.talk.micInsecureOrigin,
  unsupported: strings.talk.micUnsupported,
};

export function useTalk(options: {
  token: string;
  /**
   * 這一欄目前是否真的看得見（雙欄舞台在窄螢幕是頁籤擇一顯示，見
   * `stage/StagePage.tsx`）。⚠️ **不是**用來卸載這個畫面，而是用來在切走時把
   * 麥克風、播放器與長連線全部收掉：非活動欄只是被 CSS `hidden` 蓋住，元件仍
   * 掛著，`MediaStream` 軌道與 `display:none` 無關——不收的話麥克風指示燈會一直
   * 亮到分頁關閉，長輩以為被偷聽（`BindScreen` 的相機已為同一件事修過一次）。
   */
  visible?: boolean;
  /** 綁定失效（403）：呼叫端負責把人導回配對畫面。 */
  onBindingLost: () => void;
  deps?: Partial<TalkDeps>;
}) {
  const { token, onBindingLost, visible = true } = options;
  // ⚠️ **用 `useState` 的惰性初始化當「只算一次的常數」**（不是拿它當狀態用）：
  // `deps` 若每次重繪都重新展開成一個新物件，所有以它為相依的 `useCallback`／
  // `useEffect` 都會跟著每次重繪失效——包括那條會**重建長連線**的 effect。寫
  // 「deps 在本元件生命週期內恆定」的註解卻用 eslint-disable 硬壓下去，只是把
  // 假設藏起來；讓它真的恆定，相依陣列就可以照實寫。
  //（`useRef` 的惰性版本會踩 `react-hooks/refs`：render 期間不可讀 ref。
  //  `useMemo` 沒有「一定不會被丟掉」的保證，`useState` 有。）
  // ⚠️ 只取第一次算出的那一份：`options.deps` 之後再換不會生效——本專案沒有這種
  // 用法，測試也只在建立時注入一次。
  const [deps] = useState<TalkDeps>(() => ({
    createRecorder,
    createPlayer: createWebPlayer,
    createSocket: (url: string) => new WebSocket(url),
    postTurn: postTurnApi,
    getTurnChunk: getTurnChunkApi,
    currentPlace: currentPlaceApi,
    probeMicrophone,
    revokeQueuedReplyAudio: revokeQueuedReplyAudioImpl,
    ...options.deps,
  }));

  const [avatar, setAvatar] = useState<AvatarState>("idle");
  const [replyText, setReplyText] = useState(strings.talk.idleHint);
  const [micReady, setMicReady] = useState(false);

  // 以下全部用 ref：它們的變動不該觸發重繪，而且事件處理器必須讀到最新值
  // ——放進 state 會被閉包鎖在註冊當下的那一版。
  const recorderRef = useRef<Recorder | null>(null);
  const playerRef = useRef<WebPlayer | null>(null);
  const gestureRef = useRef(createTalkGesture());
  const socketRef = useRef<ReturnType<typeof createTalkSocket> | null>(null);
  const socketOpenRef = useRef(false);
  const playQueueRef = useRef<ReturnType<typeof createPlaybackQueue> | null>(null);
  /** 目前正在播的那一則的 uri：插嘴回收 blob URL 時要把它排除在外。 */
  const playingUriRef = useRef<string | null>(null);
  const chunkQueueRef = useRef<ChunkQueue | null>(null);
  const placeRef = useRef<Promise<ElderPlace | null> | null>(null);
  /** 這一輪開錄流程的 promise：停止前先 await，消除「放開跑在開錄完成前」的競態。 */
  const startPromiseRef = useRef<Promise<boolean>>(Promise.resolve(false));
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const thinkingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const micReadyRef = useRef(false);
  const avatarRef = useRef<AvatarState>("idle");

  const clearThinkingWatchdog = useCallback(() => {
    if (thinkingTimerRef.current !== null) {
      clearTimeout(thinkingTimerRef.current);
      thinkingTimerRef.current = null;
    }
  }, []);

  const setAvatarBoth = useCallback(
    (next: AvatarState) => {
      avatarRef.current = next;
      setAvatar(next);
      // 離開「在想」就代表有東西回來了（或是失敗已經處理過），保險可以收掉。
      if (next !== "thinking") {
        clearThinkingWatchdog();
      }
    },
    [clearThinkingWatchdog],
  );

  /** 重新起算「等不到回話」的保險（見 THINKING_TIMEOUT_MS）。 */
  const armThinkingWatchdog = useCallback(() => {
    clearThinkingWatchdog();
    thinkingTimerRef.current = setTimeout(() => {
      thinkingTimerRef.current = null;
      setReplyText(strings.talk.noAnswer);
      setAvatarBoth("idle");
    }, THINKING_TIMEOUT_MS);
  }, [clearThinkingWatchdog, setAvatarBoth]);

  // 進畫面就問麥克風權限。⚠️ 不能等長輩按下去才問——權限對話框跳出來的當下他的
  // 手指正按在鍵上，第一次錄音會被對話框吃掉（App 在 iOS 上踩過同一個坑）。
  useEffect(() => {
    let alive = true;
    void deps.probeMicrophone().then((result) => {
      if (!alive) {
        return;
      }
      const granted = result === "granted";
      micReadyRef.current = granted;
      setMicReady(granted);
      if (!granted) {
        setReplyText(MIC_PROBLEM_MESSAGES[result]);
      }
    });
    return () => {
      alive = false;
    };
  }, [deps]);

  /** 背景取下一段；取不到（409／網路／合成失敗）就記成 null，播完這段即收工。 */
  const prefetchNext = useCallback(
    (queue: ChunkQueue) => {
      if (queue.nextIndex >= queue.total) {
        queue.pending = null;
        return;
      }
      const index = queue.nextIndex;
      queue.nextIndex += 1;
      queue.pending = deps.getTurnChunk(index, queue.digest, token).catch(() => null);
    },
    [deps, token],
  );

  /** 這一段播完了：接上已在背景取好的下一段；沒有下一段就回到待機。 */
  const advanceQueue = useCallback(async () => {
    const queue = chunkQueueRef.current;
    const player = playerRef.current;
    if (!queue?.pending || player === null) {
      chunkQueueRef.current = null;
      setAvatarBoth("idle");
      return;
    }
    const chunk = await queue.pending;
    // ⚠️ 等待期間長輩又講了一句：這一輪已作廢，交給新的那一輪，不可以插播。
    if (chunkQueueRef.current !== queue) {
      return;
    }
    if (!chunk?.audio_url) {
      chunkQueueRef.current = null;
      setAvatarBoth("idle");
      return;
    }
    prefetchNext(queue);
    playingUriRef.current = chunk.audio_url;
    player.replace({ uri: chunk.audio_url });
    player.play();
  }, [prefetchNext, setAvatarBoth]);

  // 建立錄音器、播放器、播放佇列與長連線。
  //
  // ⚠️ 相依只有 `token` 與 `visible` 兩個會變的東西：`deps` 只算一次（見上方
  // `useState` 惰性初始化那段），而 `advanceQueue`／`prefetchNext`／`setAvatarBoth`／
  // `armThinkingWatchdog` 全都只隨 `token` 變。所以這條 effect 不需要 eslint-disable
  // ——它真的只在換人登入或這一欄被切走／切回來時重跑。
  useEffect(() => {
    if (!token || !visible) {
      return;
    }
    const player = deps.createPlayer();
    playerRef.current = player;
    const recorder = deps.createRecorder();
    recorderRef.current = recorder;
    // 手勢狀態機在本元件的生命週期內只有一顆，但仍先取進區域變數：cleanup 直接
    // 讀 `gestureRef.current` 會被 lint 當成「可能已經換過的 DOM 節點 ref」。
    const gesture = gestureRef.current;

    const queue = createPlaybackQueue(async (item: PlaybackItem) => {
      setAvatarBoth("speaking");
      playingUriRef.current = item.audioUrl;
      const outcome = await playAndWait(player, item);
      if (outcome === "timeout") {
        // 事件沒來、靠保險放行。留 log 而不是靜默——真的常發生的話代表音訊有
        // 別的問題，那是另一件要查的事。
        console.warn("[talk] 播放結束事件沒來，靠保險逾時放行", item.turnId);
      }
    });
    playQueueRef.current = queue;

    const subscription = player.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) {
        void advanceQueue();
      }
    });

    const socket = createTalkSocket({
      baseUrl: window.location.origin,
      token,
      createSocket: deps.createSocket,
      writeAudio: writeReplyAudio,
      onStatus: (status) => {
        socketOpenRef.current = status === "open";
      },
      onFrame: (frame: TalkFrame) => {
        // 只要後端還在跟我們說話，「等不到回話」的保險就重新起算。
        if (avatarRef.current === "thinking") {
          armThinkingWatchdog();
        }
        if (frame.type === "error") {
          setReplyText(frame.text);
          setAvatarBoth("idle");
          return;
        }
        if (frame.type === "queued") {
          // ⚠️ 靜默排隊與當機對長輩來說長得一模一樣，他只會再講一次——而那會讓
          // 已經滿載的 GPU 雪上加霜。
          setReplyText(strings.talk.queued(frame.position));
          return;
        }
        setReplyText(frame.text);
        if (frame.type === "reply") {
          // 上一輪的續拉就此作廢（advanceQueue 以物件識別比對，舊佇列自行退場）。
          chunkQueueRef.current = null;
          if (frame.chunk_count > 1 && frame.reply_digest) {
            const chunks: ChunkQueue = {
              digest: frame.reply_digest,
              total: frame.chunk_count,
              nextIndex: 1,
              pending: null,
            };
            chunkQueueRef.current = chunks;
            prefetchNext(chunks);
          }
        }
        if (frame.audio_url) {
          queue.push({
            turnId: frame.turn_id,
            audioUrl: frame.audio_url,
            text: frame.text,
            durationMs: frame.duration_ms ?? 0,
          });
        } else if (frame.type === "reply") {
          // ⚠️ 這一輪有字沒有聲音（TTS 掛掉、或音檔落地失敗——`talkSocket` 刻意
          // 仍把訊框交出來，字幕照樣有用）。不回到待機的話，畫面永遠停在「金孫
          // 想一下…」而麥克風鍵一直是停用的，長輩從此按不動。`ack` 不在此列：
          // 那只是安撫話，真正的回覆還在路上。
          setAvatarBoth("idle");
        }
      },
    });
    socketRef.current = socket;

    return () => {
      // ⚠️ 每一條資源都要在這裡收乾淨。這條 cleanup 同時涵蓋三種離開方式：長輩
      // 登出／被導回配對（元件卸載）、換人登入（token 變）、以及**這一欄被切到
      // 背景**（`visible` 變 false，窄螢幕頁籤模式）。漏掉任何一項的後果都是同
      // 一個：麥克風指示燈一直亮著、長輩以為被偷聽。
      if (longPressTimerRef.current !== null) {
        clearTimeout(longPressTimerRef.current);
        longPressTimerRef.current = null;
      }
      clearThinkingWatchdog();
      gesture.reset();
      // ⚠️ 麥克風軌道：等開錄流程跑完再停。開錄還卡在權限對話框時
      // `recorder.stop()` 是 no-op（那時 `MediaRecorder` 還沒建立），而對話框回來
      // 之後才拿到的那顆 `MediaStream` 就再也沒有人關了。
      const startPromise = startPromiseRef.current;
      startPromiseRef.current = Promise.resolve(false);
      void startPromise.then(() => recorder.stop()).catch(() => undefined);
      // 還沒播的丟掉，連同它們的 blob URL 一起回收（`clear()` 只丟項目，不回收）。
      queue.clear();
      subscription.remove();
      socket.close();
      player.dispose();
      // ⚠️ 這一行對正式的 `createWebPlayer` 是重複的（它的 `dispose()` 自己就會掃一次），
      // 刻意保留：`createPlayer` 是注入點，而 `WebPlayer` 這個型別並沒有「dispose 會回收
      // blob URL」的承諾。把回收寫在這裡，這條 cleanup 的「全部放掉」才是它自己保證的事，
      // 不是靠另一個模組的內部行為順便達成的。重複呼叫無副作用（集合已空）。
      deps.revokeQueuedReplyAudio();
      chunkQueueRef.current = null;
      placeRef.current = null;
      playingUriRef.current = null;
      socketOpenRef.current = false;
      socketRef.current = null;
      playQueueRef.current = null;
      playerRef.current = null;
      recorderRef.current = null;
      setAvatarBoth("idle");
      // ⚠️ 只在麥克風本來就沒問題時才重設字幕：拿不到麥克風的那句說明是長輩
      // 唯一的線索，切個頁籤把它洗成「按住下面的麥克風說話」，而按鈕仍然是停用
      // 的——那看起來就只是壞掉。
      if (micReadyRef.current) {
        setReplyText(strings.talk.idleHint);
      }
    };
  }, [
    token,
    visible,
    deps,
    advanceQueue,
    prefetchNext,
    setAvatarBoth,
    armThinkingWatchdog,
    clearThinkingWatchdog,
  ]);

  const startRecording = useCallback(async (): Promise<boolean> => {
    if (!micReadyRef.current || avatarRef.current === "thinking") {
      return false;
    }
    // ⚠️ 按下去就是要講話：不清掉還沒播的、不停掉正在播的，金孫自己的聲音會被
    // 錄進去。
    playQueueRef.current?.clear();
    // ⚠️ `clear()` 只把項目從佇列丟掉，那些已經造出來的 blob URL 一個都不會被
    // 回收（Task 4 刻意把回收能力放在 playback 模組、由呼叫端一起呼叫）。正在播
    // 的那一則要排除在外——它的 src 還掛在播放器上。
    deps.revokeQueuedReplyAudio(playingUriRef.current ?? undefined);
    playerRef.current?.pause();
    const started = (await recorderRef.current?.start()) ?? false;
    if (!started) {
      // ⚠️ 不講「金孫沒聽清楚」：錄音根本沒開始，那句話會讓長輩以為是自己講得
      // 不夠大聲，於是一次比一次更用力喊。
      setReplyText(strings.talk.micStartFailed);
      setAvatarBoth("idle");
      return false;
    }
    // 錄音一開始就發動取位、不 await：長輩講話的那幾秒剛好把它蓋掉，送出時
    // 通常已經好了。currentPlace 永不拋，不需要 catch。
    placeRef.current = deps.currentPlace();
    setAvatarBoth("listening");
    setReplyText(strings.talk.listening);
    return true;
  }, [deps, setAvatarBoth]);

  const stopAndSend = useCallback(async () => {
    // ⚠️ 等開錄流程完成再停。放開常比開錄先到——App 版先前用 avatar state 守門
    // 會讀到過期值而漏掉停止，造成「聆聽中」殘留、二次按壓把音檔洗掉
    //（2026-07-25 修復）。
    const started = await startPromiseRef.current;
    if (!started) {
      return;
    }
    setAvatarBoth("thinking");
    armThinkingWatchdog();
    setReplyText(strings.talk.thinking);
    try {
      const audio = await recorderRef.current?.stop();
      // ⚠️ 也擋 0 位元組：手指一碰就放、或系統把軌道搶走時，`MediaRecorder` 一
      // 個位元組都沒收到。照送的話後端只會回一句聽不懂，白白吃掉一輪 GPU。
      if (!audio || audio.byteLength === 0) {
        throw new Error("no recording");
      }
      const place = await (placeRef.current ?? Promise.resolve(null));
      placeRef.current = null;
      if (socketRef.current && socketOpenRef.current) {
        socketRef.current.sendLocation(place);
        socketRef.current.sendAudio(audio);
        return;
      }
      // 降級路徑：長連線連不上時仍然講得了話。
      const reply = await deps.postTurn(audio, token, place);
      setReplyText(reply.text);
      chunkQueueRef.current = null;
      if (reply.audio_url) {
        setAvatarBoth("speaking");
        if (reply.chunk_count > 1 && reply.reply_digest) {
          const queue: ChunkQueue = {
            digest: reply.reply_digest,
            total: reply.chunk_count,
            nextIndex: 1,
            pending: null,
          };
          chunkQueueRef.current = queue;
          prefetchNext(queue);
        }
        playingUriRef.current = reply.audio_url;
        playerRef.current?.replace({ uri: reply.audio_url });
        playerRef.current?.play();
      } else {
        setAvatarBoth("idle");
      }
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 403) {
        setReplyText(strings.talk.bindingLost);
        onBindingLost();
      } else {
        setReplyText(strings.talk.fallback);
      }
      setAvatarBoth("idle");
    }
  }, [deps, token, onBindingLost, prefetchNext, setAvatarBoth, armThinkingWatchdog]);

  const pressIn = useCallback(() => {
    // 第一次互動時解鎖音訊（iOS Safari）。必須在使用者手勢之內，之後才播得動
    // WebSocket 送下來的回覆。
    //
    // ⚠️ **這個時機是有風險的取捨**：`docs/dev/17` 記載 2026-07-18 的故障——
    // App 端當初在同一個手勢裡先播提示音再開錄，WebKit 的音訊工作階段被播放
    // 搶走，iPhone 錄到的音檔全數 ≤0.72 秒且近無聲。這裡的形狀相同（按下去 →
    // 播 50ms 無聲檔 → 立刻開錄），只是無聲檔一輩子只播一次。無頭測試環境判定
    // 不了，已列入人工驗收清單：真 iPhone 上把**第一次按下麥克風**講的那句送
    // 出去，確認 ASR 轉出完整句子。若真的重演，修法是把 `unlockAudio` 移到更早
    // 的手勢（例如進舞台的那一下），而不是動麥克風鍵本身。
    if (playerRef.current) {
      unlockAudio(playerRef.current);
    }
    const action = gestureRef.current.pressIn();
    if (action === "start") {
      // 長按門檻自己計時（網頁沒有 delayLongPress）。
      if (longPressTimerRef.current !== null) {
        clearTimeout(longPressTimerRef.current);
      }
      longPressTimerRef.current = setTimeout(() => {
        longPressTimerRef.current = null;
        gestureRef.current.longPress();
      }, LONG_PRESS_MS);
      startPromiseRef.current = startRecording().then((started) => {
        if (!started) {
          gestureRef.current.reset();
        }
        return started;
      });
    } else if (action === "stop") {
      void stopAndSend();
    }
  }, [startRecording, stopAndSend]);

  const pressOut = useCallback(() => {
    if (longPressTimerRef.current !== null) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
    const action = gestureRef.current.pressOut();
    if (action === "stop") {
      void stopAndSend();
    } else if (action === "keep") {
      // 短按切換：維持聆聽並提示。等開錄真的成功才顯示，失敗時保留錯誤訊息。
      void startPromiseRef.current.then((started) => {
        if (started) {
          setReplyText(strings.talk.listeningTapHint);
        }
      });
    }
  }, [stopAndSend]);

  return { avatar, replyText, micReady, pressIn, pressOut };
}
