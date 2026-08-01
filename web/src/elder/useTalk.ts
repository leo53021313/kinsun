/**
 * 對講機的狀態與副作用。
 *
 * ⚠️ 為什麼獨立成一個 hook：`app/src/app/elder/talk.tsx` 是 542 行的單一元件，
 * 權限、手勢、連線、播放、續拉佇列全塞在裡面。那份程式碼能動，但每一次改動都
 * 要重讀整支才知道會影響什麼。這裡把「狀態與副作用」與「畫面」切開，畫面只讀值。
 *
 * ⚠️ 依賴全部以 `deps` 注入。那不是為了測試跑得快——對講機的 bug 幾乎都是**時序**
 * 問題（放開比開錄先到、播放中又開口、補播與新一輪訊框交錯抵達），而時序只有在
 * 能精確控制每一步的環境裡才測得出來。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { apiErrorMessage, ApiError } from "@/api";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { unlockAudio } from "@/talk/audioUnlock";
import {
  createWebPlayer,
  revokeQueuedReplyAudio as revokeQueuedReplyAudioImpl,
  revokeReplyAudio as revokeReplyAudioImpl,
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

import { postTurn as postTurnApi, type ElderPlace } from "./api";
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

/**
 * 長輩插嘴時最多留幾則回覆等補播（✅ 專案裁決 2026-08-01「改回補播」）。
 *
 * 取 2 ＝**一輪最多兩則語音**（後端 `ws.py` 的 ack→reply 兩段式：安撫話一則、
 * 答案一則）。留這麼多剛好接得住「一整輪的答案」，而不會在他連續插嘴好幾次之後
 * 累積成一串舊語音——那時最後補播的是幾分鐘前的問題，對長輩來說就是金孫在自言
 * 自語（那正是 2026-07-31 選擇丟棄時的顧慮，用上限把它壓在可接受的範圍）。
 *
 * 滿了就擠掉**最舊**的那一則並回收它的音檔：越晚抵達的越接近他現在關心的事。
 */
const MAX_DEFERRED_REPLIES = 2;

export type TalkDeps = {
  createRecorder: () => Recorder;
  createPlayer: () => WebPlayer;
  createSocket: (url: string) => WebSocket;
  postTurn: typeof postTurnApi;
  currentPlace: typeof currentPlaceApi;
  probeMicrophone: typeof probeMicrophone;
  /** 回收「造出來了卻還沒播到」的 blob URL（見 `talk/playback.ts`）。 */
  revokeQueuedReplyAudio: typeof revokeQueuedReplyAudioImpl;
  /** 回收**單獨一則**確定不會再播的回覆音檔（補播佇列滿了、擠掉最舊那一則時用）。 */
  revokeReplyAudio: typeof revokeReplyAudioImpl;
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
  /**
   * 後端不認這支 token（401）：呼叫端負責清掉登入並把人導回配對畫面。
   *
   * ⚠️ **與 403 分開接，因為 403 幾乎到不了**：家屬按「重新產生長輩綁定碼」時，
   * 後端 `accounts/service.py::revoke_elder_device` 是**先**撤 token **再**拆綁定，
   * 於是 `channels/app/turns.py::current_elder` 在認證那一步就回 401，永遠走不到
   * 後面那個 403 `consent_revoked`。只接 403 的話，長輩每按一次麥克風都只會看到
   * 「金孫沒聽清楚，再說一次好嗎？」，重新整理也沒用（token 在 localStorage、
   * 初始路由仍是對講機），而家屬手上那組新碼永遠沒有畫面可以輸入。
   * ⚠️ 彩排後重建資料庫會讓舊 token 落在同一個狀態，比家屬按鈕更容易發生。
   */
  onTokenRevoked: () => void;
  deps?: Partial<TalkDeps>;
}) {
  const { token, onBindingLost, onTokenRevoked, visible = true } = options;
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
    currentPlace: currentPlaceApi,
    probeMicrophone,
    revokeQueuedReplyAudio: revokeQueuedReplyAudioImpl,
    revokeReplyAudio: revokeReplyAudioImpl,
    ...options.deps,
  }));

  const [avatar, setAvatar] = useState<AvatarState>("idle");
  const [replyText, setReplyText] = useState(strings.talk.idleHint);
  const [micReady, setMicReady] = useState(false);

  // 401 的判定沿用家屬端五個畫面都在用的那一支（`session/useSignOutOnAuthError.ts`）
  // ——「什麼算 token 不能用了」只該有一份定義。⚠️ 它只負責「收到 401 就呼叫你給的
  // 那支函式」，長輩要看到的那句說明由呼叫端在配對畫面上講（見下方 catch 的說明）。
  // 用 `useMemo` 而非 `useCallback`：它是**工廠**、回傳的是函式值（同家屬端寫法）。
  const signOutOn401 = useMemo(() => makeSignOutOnAuthError(onTokenRevoked), [onTokenRevoked]);

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
  /**
   * 目前正在播的那一則屬於**哪一輪**。
   *
   * ⚠️ `onFrame` 據此判斷「現在正在播的是別一輪的聲音」，那時新一輪的字不可以先把
   * 字幕搶走——否則長輩聽到藥的答案、看到公車的字。
   *
   * （2026-08-01 續段直送：這個 ref 原本還有第二個消費者——`advanceQueue` 用它確認
   * 「要接的續段」與「剛播完的那一則」是同一輪。REST 續拉整套移除之後那個用途已經
   * 不存在，見 `advanceQueue` 該處說明。）
   */
  const playingTurnIdRef = useRef<string | null>(null);
  const placeRef = useRef<Promise<ElderPlace | null> | null>(null);
  /** 這一輪開錄流程的 promise：停止前先 await，消除「放開跑在開錄完成前」的競態。 */
  const startPromiseRef = useRef<Promise<boolean>>(Promise.resolve(false));
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const thinkingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const micReadyRef = useRef(false);
  const avatarRef = useRef<AvatarState>("idle");
  /**
   * 麥克風正在收音（從按下去到 `recorder.stop()` 回來為止）。
   *
   * ⚠️ 刻意不用 `avatar === "listening"` 代替：那個值要等 `recorder.start()` 解出
   * 之後才設，而清佇列／暫停播放在 `await` 之前就發生了——中間那段窗口正是「訊框
   * 剛好這時抵達」會出事的地方。
   */
  const micActiveRef = useRef(false);
  /**
   * 收音期間收下來、等他講完再補播的那幾則回覆。
   *
   * ✅ **補播而不是丟棄**（專案裁決 2026-08-01，推翻 2026-07-31 的「一律丟棄」）：
   * **插嘴照樣要能打斷，但前一題的答案不要丟掉。**長輩問了 A、等不及改問 B，
   * A 的答案在他講 B 的時候才回來——丟掉的話那一題就永遠沒有答案了，而他問的
   * 是「我的藥要吃幾顆」這種真的需要答案的事。
   *
   * ⚠️ **補播的語意是「等他講完、送出之後才播」，不是「錄音期間照樣播」**：
   * 收音中放音的話金孫自己的聲音會被錄進 ASR（P3 Task 8 Critical 2）。這個
   * 保護一行都沒有鬆動——播放回呼看到 `micActiveRef` 為真就把那一則收進這裡，
   * 由 `stopAndSend` 的 `finally` 在收音真的結束之後才放回播放佇列。
   *
   * ⚠️ **正在播的那一則不收進來**：他已經聽到一部分了，從頭再放一次比較像故障。
   */
  const deferredRepliesRef = useRef<PlaybackItem[]>([]);
  /** 中止「正在播的那一則」的等待（見播放回呼裡的 Promise.race）。 */
  const abortPlaybackRef = useRef<(() => void) | null>(null);

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

  // 進畫面就暖定位權限（F-17 第二段，2026-08-01）。⚠️ 與上面 `probeMicrophone`
  // 那條同一個理由、刻意獨立成另一條 effect（不合併進去、不改動上面那條的邏輯
  // 與相依陣列）：權限對話框跳出來的當下長輩的手指可能正按在麥克風鍵上，等他
  // 按下去才問，開錄手勢會被系統面板搶走指標——與麥克風權限同一個坑，見
  // `elder/location.ts` 檔頭。
  //
  // ⚠️ 這裡刻意**不使用**解出的值：目的只是讓瀏覽器把「允許／拒絕」這個決定在
  // 安全的時機問完。`startRecording()` 需要的實際座標仍由它自己那一行
  // `deps.currentPlace()` 取得（未改動）——同一 origin 的定位權限只會跳一次
  // 對話框，之後的呼叫直接用瀏覽器自己的位置快取（`maximumAge`，見
  // `location.ts`），不會在錄音進行中再跳窗。定位權限被拒或逾時不影響對講機
  // 本身：`currentPlace()` 一律以 `null` 收尾，金孫照舊開口問所在地。
  useEffect(() => {
    void deps.currentPlace();
  }, [deps]);

  /**
   * 把收音期間收下來的那幾則放回播放佇列（收音真的結束之後才可以呼叫）。
   *
   * ⚠️ **順序：舊的先播、新問題的答案後播**（FIFO，就是丟回同一條佇列的自然結果）。
   * 理由有二：①舊答案**現在就在手上**，而新問題的答案還要等後端跑五到十秒——先播舊
   * 的正好把那段空白填掉，反過來排的話長輩會先面對一段沉默、再聽到一句更久以前的
   * 答案；②字幕跟著真的播出來的那一則走（見播放回呼），舊答案播出來時畫面上就是
   * 它自己的字，長輩看得到這句話在回答什麼。
   */
  const flushDeferredReplies = useCallback(() => {
    const queue = playQueueRef.current;
    if (queue === null || deferredRepliesRef.current.length === 0) {
      return;
    }
    const pending = deferredRepliesRef.current;
    deferredRepliesRef.current = [];
    for (const item of pending) {
      queue.push(item);
    }
  }, []);

  /**
   * 這一則播完了：若播放佇列已經空了，畫面回到待機；還有東西排著就什麼都不做
   * ——那些是續段（`chunk` 訊框）或別一輪的 ack／reply，播放佇列自己的 `drain()`
   * 會接著播下去，不需要這裡插手。
   *
   * ⚠️ **這裡以前還有「輪次比對＋去 REST 拉下一段」的邏輯，2026-08-01 隨續拉
   * 整套移除**（見 `459051f`）：REST 續拉時代，`chunkQueueRef` 是單一、會被
   * 補播覆寫的「目前正在追的續拉狀態」，`advanceQueue` 得先確認「剛播完的那一則」
   * 與「現在的續拉佇列」是同一輪，否則會把新那一輪的續段接在舊答案後面。改成
   * WS 主動推之後，續段訊框直接 `queue.push()` 進同一條 FIFO 播放佇列（見下方
   * `onFrame`），**沒有人在猜『下一段該向誰要』**——那個會被覆寫的共用可變狀態
   * 不存在了，輪次比對因此變成恆假的死碼，一併拿掉。
   *
   * ⚠️ **殘留風險（尚未實測，僅為理論推導）**：播放順序現在完全由訊框的**抵達
   * 順序**決定，不是「正確順序」。長輩問 A（會切成多段）沒等完就問 B：續段
   * 每段合成約 2.3–3.6 秒、`speech/chunking.py::MAX_CHUNKS = 4`（A 最多 3 段
   * 續段，約 7–10 秒）；B 整輪（ASR＋LLM＋TTS）約 8–15 秒——兩個時間範圍重疊，
   * 所以「A 的後段比 B 的整輪還慢送達」是低機率但真實存在的可能。一旦發生，
   * 佇列順序會變成 `[A0, B0, A1]`：長輩聽到 A 的開頭、B 的完整答案、然後 A 的
   * 第二句才冒出來——正是 `459051f` 當初要消滅的那種聽感，只是觸發條件從「補播
   * 交錯」換成「後段合成比下一輪整輪還慢送達」。**這個任務刻意不加新的守門**
   * （按輪分組或丟棄過期段需要另外設計），只在此記錄，供下一次處理續段時序時
   * 參考。
   */
  const advanceQueue = useCallback(() => {
    if ((playQueueRef.current?.size() ?? 0) === 0) {
      setAvatarBoth("idle");
    }
  }, [setAvatarBoth]);

  // 建立錄音器、播放器、播放佇列與長連線。
  //
  // ⚠️ 相依只有 `token` 與 `visible` 兩個會變的東西：`deps` 只算一次（見上方
  // `useState` 惰性初始化那段），而 `advanceQueue`／`setAvatarBoth`／
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
      // ⚠️ 長輩正按著麥克風：這一則**先收下來、等他講完再補播**（✅ 專案裁決
      // 2026-08-01，見 `deferredRepliesRef` 的說明）。放出去的話金孫自己的聲音會被
      // 錄進去——後端是明文設計的 ack→reply 兩段式，「安撫話播完、長輩不耐煩開口問
      // 下一句、第一輪的真正答案這時才回來」是常態而不是邊角。
      // ⚠️ 這裡**不可以**回收它的 blob URL：那個音檔待會兒還要播。
      if (micActiveRef.current) {
        const pending = deferredRepliesRef.current;
        pending.push(item);
        while (pending.length > MAX_DEFERRED_REPLIES) {
          // 擠掉最舊的那一則。它從此不會再被 replace()，這裡不回收就沒有人回收了
          //（⚠️ 用只收一則的 `revokeReplyAudio`，不可用「除了這一則以外全部回收」
          //  的 `revokeQueuedReplyAudio`——後者會把還要補播的那幾則一起回收掉）。
          deps.revokeReplyAudio(pending.shift()!.audioUrl);
        }
        return;
      }
      setAvatarBoth("speaking");
      playingUriRef.current = item.audioUrl;
      // 記下「現在播的是哪一輪」：字幕不可被別一輪搶走（見下方 `isSpeakingAnotherTurn`）。
      playingTurnIdRef.current = item.turnId;
      // 字幕跟著**真的播出來的那一則**走：收音期間收下來的那幾則，字幕要等補播時
      // 才顯示，否則長輩聽到的跟看到的是兩件事。
      if (item.text) {
        setReplyText(item.text);
      }
      // ⚠️ **與「被打斷」賽跑**：`player.pause()` 之後 `didJustFinish` 永遠不會來，
      // `playAndWait` 只能等滿「時長＋3 秒」的保險才放行；而那期間
      // `createPlaybackQueue` 的 `running` 是 true，新回覆只能排隊。一則 30 秒的
      // 回覆被打斷後，下一句的語音要等 29 秒才播得出來，這 29 秒內 avatar 停在
      // 「在想」、麥克風鍵按不動——正是本模組其他地方拚命要避免的那種卡死，只是
      // 換一條路徑進來。⚠️ 修在這一層，不動搬移過來的 `talkSocket.ts`。
      //
      // 被搶走的那顆 `playAndWait` 仍會在自己的保險逾時後自行收尾（移除監聽、清
      // 計時器），不會洩漏；它之後解出來的值沒有人要，這正是我們要的。
      const outcome = await Promise.race([
        playAndWait(player, item),
        new Promise<"aborted">((resolve) => {
          abortPlaybackRef.current = () => resolve("aborted");
        }),
      ]);
      abortPlaybackRef.current = null;
      if (outcome === "timeout") {
        // 事件沒來、靠保險放行。留 log 而不是靜默——真的常發生的話代表音訊有
        // 別的問題，那是另一件要查的事。
        console.warn("[talk] 播放結束事件沒來，靠保險逾時放行", item.turnId);
      }
    });
    playQueueRef.current = queue;

    const subscription = player.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) {
        advanceQueue();
      }
    });

    // ⚠️ **iOS 音訊解鎖提早到「這顆播放器誕生後的第一個觸碰」**（✅ 專案裁決
    // 2026-08-01，選項 B）。`docs/dev/17` 記載 2026-07-18 的真實故障：App 端在
    // 開錄的同一個手勢裡先播提示音，WebKit 的音訊工作階段被播放搶走，iPhone
    // 錄到的音檔**全數 ≤0.72 秒且近無聲**；修法是「開錄的那一刻不要播任何東西」。
    // 解鎖若只掛在麥克風鍵上（`pressIn`），形狀與那次故障相同。
    //
    // ⚠️ **為什麼掛在這裡、而不是配對／登入畫面的按鈕上**：iOS 的解鎖綁在單一
    // `HTMLMediaElement` 上（見 `audioUnlock.ts` 的 `WeakSet` 說明），而播放器是
    // 這條 effect 造出來的——長輩按下「開始使用」的那一刻 `playerRef.current` 還是
    // `null`，在那個手勢裡解鎖只會解鎖一顆不存在（或下一顆會被丟掉）的播放器，
    // 等於沒解鎖。所以「更早」的上界就是**這顆播放器誕生之後的第一個手勢**。
    //
    // ⚠️ 兩道守門：
    // ①**金孫正在講話時不解鎖**——`unlockAudio` 會 `replace()` 播放器的來源，等於把
    //   他講到一半的那句話**當場切斷**並回收它的 blob URL。長輩按一下鈴鐺就把回覆
    //   打斷，會是這條監聽器自己製造出來的新故障。
    //   ⚠️ 判斷用 `avatarRef === "speaking"` **加上** `queue.isPlaying()`，不可只看後者
    //   （2026-08-01 審查 Minor 1）：`createPlaybackQueue` 的 `running` 只在佇列回呼
    //   執行期間為真，而 `advanceQueue` 播的第 2 段以後、以及 `stopAndSend` 的 POST
    //   降級路徑**都不經佇列**——只看 `isPlaying()` 的話，那兩段期間的觸碰照樣會把
    //   聲音切掉。`speaking` 涵蓋這三者（播放開始時設、續段放完才回到 `idle`）；
    //   `isPlaying()` 則多守住「已推進佇列、drain 還沒起跑」那一瞬。
    // ②`micActiveRef` 為真時不解鎖——長輩正按著麥克風講話，這時放任何聲音都會被
    //   錄進去（P3 Task 8 Critical 2 守的就是這件事）。
    //   ⚠️ **誠實記載這一道的份量**：以目前的形狀它獨自承重不起來，也測不出來
    //   ——`pressIn` 的補漏呼叫一定跑在 `micActiveRef` 轉真之前，收音中的播放器
    //   必然已經解鎖過，`unlockAudio` 自己就會早退。留著是因為它守的是一個很可能
    //   被改動的形狀：只要有人以「解鎖已經提早了」為由刪掉 `pressIn` 那一行，
    //   「播放中插嘴」這條路徑（守門①擋掉解鎖）就會留下一顆未解鎖的播放器，而
    //   長輩按住麥克風期間的任何一次觸碰都會把無聲檔放進他的錄音裡。
    // 兩種情形下都不移除監聽器：下一次觸碰再試。
    const unlockOnFirstGesture = () => {
      if (micActiveRef.current || avatarRef.current === "speaking" || queue.isPlaying()) {
        return;
      }
      unlockAudio(player);
      window.removeEventListener("pointerdown", unlockOnFirstGesture, true);
    };
    // capture：比 React 掛在根節點上的 `onPointerDown` 更早跑到。若長輩進畫面後
    // 第一個動作就是按麥克風，這一下仍與開錄同一個手勢（形狀與改動前相同，麥克風
    // 鍵那裡的呼叫是補漏）——真正被這條救到的是「先按過鈴鐺／登出／碰過畫面任何
    // 一處／碰過另一欄」的路徑，以及畢典展示時操作者在電腦上先點過東西的路徑。
    window.addEventListener("pointerdown", unlockOnFirstGesture, true);

    // ⚠️ 這一輪 effect 是否已經收掉。舊連線的 `onclose`／`onerror` 可能在新連線的
    // `onopen` **之後**才抵達（快速切走再切回來），沒有這道守門的話它會把
    // `socketOpenRef` 洗回 false——那一輪於是退回 POST 降級，講得了話但沒有安撫話、
    // 延遲較長。晚到的訊框同理，不該再影響已經換人的畫面。
    let disposed = false;

    const socket = createTalkSocket({
      baseUrl: window.location.origin,
      token,
      createSocket: deps.createSocket,
      writeAudio: writeReplyAudio,
      onStatus: (status) => {
        if (disposed) {
          return;
        }
        socketOpenRef.current = status === "open";
      },
      onFrame: (frame: TalkFrame) => {
        if (disposed) {
          return;
        }
        // 只要後端還在跟我們說話，「等不到回話」的保險就重新起算。
        if (avatarRef.current === "thinking") {
          armThinkingWatchdog();
        }
        // ⚠️ 長輩正按著麥克風時，畫面歸他：不要用上一輪的字蓋掉「金孫在聽…」，
        // 也不要把 avatar 從「在聽」搶走。那一則的字幕會在它真的播出來的時候補上
        //（見上面的播放回呼）。
        const canTakeOverScreen = !micActiveRef.current;
        // ⚠️ **字幕另有一道守門**（2026-08-01 審查 Important，補播引入）：現在正在播的
        // 若是**別一輪**的聲音（補播舊答案時就是這種情形），這一輪的字不可以現在就蓋
        // 上去——實測長輩會在聽「您的血壓藥早上吃一顆」的同時看到「好，我幫您查一下
        // 喔」，而舊答案還要播八秒。那正是本檔播放回呼自己寫下要避免的事（「否則長輩
        // 聽到的跟看到的是兩件事」），對重聽的長輩尤其嚴重：字幕是他取得答案的另一半
        // 通道。
        // ⚠️ **只擋「自己會帶著聲音出場」的那些字**（`audio_url` 非空）：它們的字會在
        // 自己的聲音播出來時補上（見播放回呼）。錯誤、排隊、以及有字沒聲音的回覆沒有
        // 第二次機會，照顯示。
        const isSpeakingAnotherTurn =
          avatarRef.current === "speaking" &&
          playingTurnIdRef.current !== null &&
          playingTurnIdRef.current !== frame.turn_id;
        if (frame.type === "error") {
          // 錯誤訊息照顯示（長輩需要知道），但收音中不動 avatar。
          setReplyText(frame.text);
          if (canTakeOverScreen) {
            setAvatarBoth("idle");
          }
          return;
        }
        if (frame.type === "queued") {
          // ⚠️ 靜默排隊與當機對長輩來說長得一模一樣，他只會再講一次——而那會讓
          // 已經滿載的 GPU 雪上加霜。
          if (canTakeOverScreen) {
            setReplyText(strings.talk.queued(frame.position));
          }
          return;
        }
        // 走到這裡只剩 `ack`／`reply`／`chunk`，三者都有 `audio_url` 欄位（型別
        // 收窄後才讀）。
        const canTakeOverSubtitle =
          canTakeOverScreen && !(Boolean(frame.audio_url) && isSpeakingAnotherTurn);
        if (canTakeOverSubtitle) {
          setReplyText(frame.text);
        }
        // ⚠️ 續段直送（2026-08-01）的 `chunk` 訊框刻意**不**另開分支：它與
        // `ack`／`reply` 共用同一組欄位（`turn_id`／`audio_url`／`text`／
        // `duration_ms`），這段既有的通用推播邏輯結構上就完整涵蓋了它——
        // `audio_url` 非空就推進佇列，空音檔（後端合成失敗、或本來就切不出
        // 第二段時補送的終止訊框）因為這裡的判斷式為假而自然不進佇列，不需要
        // 額外判斷 `is_last`（全檔沒有任何地方讀這個欄位，終止與否單純看
        // `audio_url` 是否為空）。加一個功能重複的 `chunk` 專屬分支只會製造
        // 「兩段程式碼做同一件事、忘記讓其中一段先 return 就重複推播」的風險
        // ——見 2026-08-01 移除 REST 續拉（`getTurnChunk`／`prefetchNext`／
        // `ChunkQueue`）那次 commit 的訊息：舊碼曾經讓 `chunk_count > 1` 同時
        // 觸發這裡的推播**與**已刪除的 REST 續拉，造成同一段語音被播兩次。
        // ⚠️ **這裡是唯一還在守住續段行為的地方**：日後若有人把這段收窄成
        // 只認 `frame.type === "ack" || frame.type === "reply"`，續段會在這裡
        // 被悄悄濾掉、靜默失效（不會噴錯，只是長輩再也聽不到第二段以後的話）
        // ——改動這段判斷式前請先確認 `chunk` 訊框仍然吃得到。
        if (frame.audio_url) {
          queue.push({
            turnId: frame.turn_id,
            audioUrl: frame.audio_url,
            text: frame.text,
            durationMs: frame.duration_ms ?? 0,
          });
        } else if (frame.type === "reply" && canTakeOverScreen) {
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
      disposed = true;
      // 解鎖監聽器綁的是**這一顆**播放器；下一輪 effect 會為新播放器再掛一條。
      window.removeEventListener("pointerdown", unlockOnFirstGesture, true);
      // 收音狀態與等補播的那幾則一併歸零：這一輪的播放器與長連線都要丟掉了，
      // 留著只會讓切回來（或換人登入）之後的第一件事變成播一段上一輪的舊回覆。
      // 它們的 blob URL 由下面那一支不帶例外的 `revokeQueuedReplyAudio()` 全掃回收。
      micActiveRef.current = false;
      deferredRepliesRef.current = [];
      abortPlaybackRef.current?.();
      abortPlaybackRef.current = null;
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
      placeRef.current = null;
      playingUriRef.current = null;
      playingTurnIdRef.current = null;
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
  }, [token, visible, deps, advanceQueue, setAvatarBoth, armThinkingWatchdog, clearThinkingWatchdog]);

  const startRecording = useCallback(async (): Promise<boolean> => {
    if (!micReadyRef.current || avatarRef.current === "thinking") {
      return false;
    }
    // ⚠️ 從這一刻起就算「收音中」，而不是等 `recorder.start()` 解出之後——中間那段
    // 等權限／等裝置的窗口裡若有訊框抵達，照播的話一樣會被錄進去。
    micActiveRef.current = true;
    // ⚠️ 按下去就是要講話：不停掉正在播的，金孫自己的聲音會被錄進去。
    // ⚠️ 中止「正在播的那一則」的等待。只 `pause()` 的話 `didJustFinish` 永遠不會
    // 來，播放佇列會被卡住整整「時長＋3 秒」，下一輪的語音得排在後面（見播放回呼）。
    abortPlaybackRef.current?.();
    abortPlaybackRef.current = null;
    playerRef.current?.pause();
    // ⚠️ **佇列刻意不 `clear()`、blob URL 也刻意不回收**（✅ 裁決 2026-08-01 改回
    // 補播，推翻 2026-07-31 的「一律丟棄」）：`micActiveRef` 上面已經轉真，drain
    // 會把排隊中那幾則一則一則交給播放回呼，回呼看到收音中就收進
    // `deferredRepliesRef` 等他講完再播。這裡若照舊清掉並回收，那些音檔就沒了。
    const started = (await recorderRef.current?.start()) ?? false;
    if (!started) {
      micActiveRef.current = false;
      // ⚠️ **這是本輪唯一仍然丟棄的路徑**：長輩根本沒問出新問題，畫面上唯一該講
      // 的是「麥克風打不開，請再按一次試試看」——那是他自救的唯一線索。補播的話
      // 字幕會被那一則自己的字**當場蓋掉**（字幕跟著真的播出來的那一則走），他就
      // 只知道金孫在講一段聽過的話、不知道麥克風沒開成。故連同還排在佇列裡的一起
      // 丟掉並回收（`clear()` 只丟項目、不回收 blob URL，兩件事要一起做）。
      playQueueRef.current?.clear();
      deferredRepliesRef.current = [];
      // 正在播（已暫停）的那一則要留著——它的 src 還掛在播放器上。
      deps.revokeQueuedReplyAudio(playingUriRef.current ?? undefined);
      // ⚠️ 不講「金孫沒聽清楚」：錄音根本沒開始，那句話會讓長輩以為是自己講得
      // 不夠大聲，於是一次比一次更用力喊。
      setReplyText(strings.talk.micStartFailed);
      setAvatarBoth("idle");
      return false;
    }
    // 錄音一開始就發動取位、不 await：長輩講話的那幾秒剛好把它蓋掉，送出時
    // 通常已經好了。currentPlace 永不拋，不需要 catch。
    //
    // ⚠️ 這裡**不會**在錄音進行中跳出定位權限對話框（F-17 第二段已解，
    // 2026-08-01）：權限請求已經在進畫面時的 mount effect 問過一次（見上方
    // 與 `probeMicrophone` 並列的那條），這裡呼叫到的是瀏覽器已經解出的權限
    // 狀態＋位置快取（`maximumAge`，見 `elder/location.ts`），不會再跳窗。
    // 這一行只負責「拿已經有的值」，不負責問權限——那件事永遠只在 mount 時做。
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
      // 收音結束（無論後面送不送得出去）：畫面與播放權還給金孫。
      micActiveRef.current = false;
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
      // ⚠️ 後端 POST /turns 已不分段（Task 1）：`reply.chunk_count` 這條路徑上
      // 恆為 1，這裡不需要（也不應該）再處理續段。
      const reply = await deps.postTurn(audio, token, place);
      setReplyText(reply.text);
      if (reply.audio_url) {
        setAvatarBoth("speaking");
        // ⚠️ POST 降級路徑的回應（`TurnReply`）**沒有 `turn_id` 這個欄位**，改用同一輪
        // 內唯一的 `reply_digest` 當輪次識別：`onFrame` 的字幕守門（見
        // `isSpeakingAnotherTurn`）據此判斷「現在播的是哪一輪」，萬一長連線稍後才
        // 接上、送來帶真 `turn_id` 的訊框，比對不合正是我們要的結果（不讓別一輪的
        // 字幕搶過來）。
        const replyTurnId = reply.reply_digest;
        playingUriRef.current = reply.audio_url;
        playingTurnIdRef.current = replyTurnId;
        playerRef.current?.replace({ uri: reply.audio_url });
        playerRef.current?.play();
      } else {
        setAvatarBoth("idle");
      }
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 403) {
        setReplyText(strings.talk.bindingLost);
        onBindingLost();
      } else if (signOutOn401(exc)) {
        // ⚠️ 401 刻意**不**設字幕：呼叫端收到就會清掉登入，這個畫面在同一次重繪
        // 就被配對畫面換掉，寫在這裡長輩看不到。那句「家人幫您重新設定了…」由
        // `ElderApp` 交給配對畫面顯示——那才是他接下來看得到的地方。
      } else {
        // ⚠️ 後端寫好的那句話照顯示，不可以一律收斂成「金孫沒聽清楚，再說一次好嗎？」
        //（全分支審查的 Important 1）。被吃掉的至少有四句：容量閘門排隊逾時（503）與
        // 每分鐘保險絲（429）的婉拒話「金孫還在忙前面那幾句，等一下下再跟您說好嗎？」、
        // 音檔太大（413）的「音檔太大，請縮短錄音再試一次」、以及語音服務不可用（503
        // `speech_unavailable`）。
        //
        // 失效情境：GPU 滿載、長連線又剛好連不上（隧道抖一下）→ 長輩講一句 → 503 →
        // 他看到「沒聽清楚」→ **更大聲再講一次** → 又一輪打進已經滿載的閘門。閘門存在
        // 的理由就是避免這件事，而降級路徑親手製造它。WS 路徑（`ws.py` 的 error 訊框）
        // 一直是照顯示的——兩條路徑對長輩說兩種話，正好違反 `turns.py` 自己寫下的意圖。
        //
        // `apiErrorMessage` 擋掉不是人話的那一種：隧道回 502 HTML、後端未捕捉例外走
        // Starlette 預設處理時，`shared/client.ts` 會自造 `http_<status>` 的英文訊息
        //（如「HTTP 502」），那種一律退回 `fallback`；非 ApiError 的例外（如錄到空音檔
        // 時本檔自己擲的 `no recording`）同理。
        setReplyText(apiErrorMessage(exc, strings.talk.fallback));
      }
      setAvatarBoth("idle");
    } finally {
      // ⚠️ 放在 finally：長連線那條路徑是 `return` 出去的，而 `recorder.stop()`
      // 本身理論上不擲例外但不該把這件事賭在上面。收音狀態若沒放開，之後每一則
      // 回覆都會被當成「錄音中抵達」而收進補播佇列——長輩從此聽不到任何回答。
      micActiveRef.current = false;
      // ⚠️ **補播就在這一刻**，而且只能在這一刻：收音已經真的結束（`stop()` 回來
      // 了），放音不會再被錄進去。刻意也在失敗路徑上補播——上一題的答案不會因為
      // 這一題送不出去就變得不值得聽。
      flushDeferredReplies();
    }
  }, [
    deps,
    token,
    onBindingLost,
    signOutOn401,
    setAvatarBoth,
    armThinkingWatchdog,
    flushDeferredReplies,
  ]);

  const pressIn = useCallback(() => {
    // 解鎖音訊（iOS Safari）的**補漏**呼叫。主要時機已移到「這顆播放器誕生後的
    // 第一個觸碰」（見上方 effect 內的 `unlockOnFirstGesture`）；長輩若在那之前
    // 碰過畫面上任何東西，這裡的呼叫就會早退（`audioUnlock` 的 `WeakSet` 記著
    // 這顆播放器解過了）。
    //
    // ⚠️ **不可以刪掉這一行**：若長輩進畫面後第一個動作就是按麥克風，`window` 上
    // 那條監聽器是在同一個手勢裡跑的（capture 階段，比這裡更早一點點），此處確實
    // 是 no-op；但若那一下剛好被監聽器的兩道守門擋掉（正在播回覆時插嘴），解鎖
    // 就只剩這裡。沒有這一行，那顆播放器可能**從未在使用者手勢內被 `play()`
    // 過**，之後 WebSocket 送下來的回覆一律被 iOS 擋下、rejection 被
    // `playback.ts` 吞掉——長輩只看得到字、聽不到任何聲音（P3 Task 8 Critical 1）。
    //
    // ⚠️ 這一路仍然**無法在無頭環境判定**（jsdom 沒有音訊工作階段），人工驗收
    // 清單照列：真 iPhone 上把**第一次按下麥克風**講的那句送出去，確認 ASR 轉出
    // 完整句子而不是空字串（2026-07-18 的 ≤0.72 秒近無聲）。
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
