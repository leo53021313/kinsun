import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioRecorder,
} from "expo-audio";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import * as Haptics from "expo-haptics";
import * as Location from "expo-location";
import { ArrowClockwiseIcon } from "phosphor-react-native/src/icons/ArrowClockwise";
import { CaretDownIcon } from "phosphor-react-native/src/icons/CaretDown";
import { ChatCircleDotsIcon } from "phosphor-react-native/src/icons/ChatCircleDots";
import { CheckCircleIcon } from "phosphor-react-native/src/icons/CheckCircle";
import { SignOutIcon } from "phosphor-react-native/src/icons/SignOut";
import { SpeakerHighIcon } from "phosphor-react-native/src/icons/SpeakerHigh";
import { WaveformIcon } from "phosphor-react-native/src/icons/Waveform";
import { WifiSlashIcon } from "phosphor-react-native/src/icons/WifiSlash";
import {
  Alert,
  Animated,
  Easing,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { BearStage, type BearSystemState } from "@/components/BearStage";
import { BellIcon } from "@/components/BellIcon";
import { MicIcon } from "@/components/MicIcon";
import { RoleSwitcher } from "@/components/RoleSwitcher";
import {
  ApiError,
  listElderNotifications,
  logoutSession,
  postTurn,
} from "@/lib/api";
import { type ElderPlace, currentPlace } from "@/lib/location";
import { loadSeenAt } from "@/lib/notificationsSeen";
import type { OttoSpeechCue } from "@/lib/ottoBridge";
import { purgeReplyAudio, writeReplyAudio } from "@/lib/replyAudio";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { createTalkGesture } from "@/lib/talkGesture";
import {
  getTalkPresentation,
  getTalkSocketFrameArrivalState,
  getTalkSocketPlaybackCompletionState,
  type ListeningMode,
  type TalkVisualState,
} from "@/lib/talkPresentation";
import {
  createPlaybackQueue,
  createTalkSocket,
  playAndWait,
  type PlaybackItem,
  type TalkFrame,
} from "@/lib/talkSocket";
import {
  applyReplyContentFrame,
  collapsedReplySummary,
  firstReplyAudioText,
  hasPlayableReplyAudio,
  shouldScrollTalkContent,
} from "@/lib/talkReplyPresentation";
import { appendTurn, clearToday } from "@/lib/todayLog";
import { colors, elder, elderGradient, motion, spacing, talkState } from "@/lib/theme";

type QueuedTalkFrame = { type: "queued"; turn_id: string; position: number };
type ChunkTalkFrame = {
  type: "chunk";
  turn_id: string;
  index: number;
  text: string;
  audio_url: string;
  duration_ms: number;
  is_last: boolean;
};
type RuntimeTalkFrame = TalkFrame | QueuedTalkFrame | ChunkTalkFrame;

type TurnDraft = {
  transcript: string;
  reply: string;
  pendingAudio: number;
  finalReceived: boolean;
  logged: boolean;
};

/**
 * 對講機：兩種說話方式（2026-07-25）→ 阿白回覆（文字放大＋自動播放語音）。
 * - 按住說話：按住聆聽、放開送出。
 * - 短按切換：按一下開始聆聽、說完再按一下送出。
 */
export default function ElderTalk() {
  const router = useRouter();
  const { fontScale, height: windowHeight } = useWindowDimensions();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const player = useAudioPlayer();
  // 結束提示音（✅ D-48 丁-2）：放開後播一聲確認「送出了」。起始不再播提示音——iOS 上
  // 播放會把音訊工作階段切到播放類別、與錄音相衝，導致錄音在約 0.6 秒被靜默中斷
  // （2026-07-18 診斷），起始改以觸覺＋畫面提示代替。
  const stopBeep = useAudioPlayer(require("@/assets/sounds/record-stop.wav"));
  const [avatar, setAvatar] = useState<BearSystemState>("idle");
  const [listeningMode, setListeningMode] = useState<ListeningMode | null>(null);
  const [replyText, setReplyText] = useState<string>(strings.talk.idleHint);
  const [transcriptText, setTranscriptText] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  // 後端尚未回傳回應情緒；先保留呈現層接點，不讓它影響五個系統態。
  const [replyEmotion] = useState<string | null>(null);
  // 每一段實際開始播放時才更新；Otto 依 text＋durationMs 對嘴，同一句重播也會
  // 因 key 不同而重新播放。這個 state 只服務呈現層，不新增 TalkVisualState。
  const [speechCue, setSpeechCue] = useState<OttoSpeechCue | null>(null);
  const [micReady, setMicReady] = useState(false);
  // 未讀提醒數（X-01，2026-07-29）：比已讀水位新的提醒數；載入失敗保持 0，
  // 對講機主功能不受影響——鈴鐺是加分項，不可讓它擋住長輩說話。
  const [unreadCount, setUnreadCount] = useState(0);
  // 內測權限狀態列用（麥克風狀態沿用 micReady）。
  const [locationGranted, setLocationGranted] = useState(false);
  // 這輪的取位 promise：錄音開始時發動，送出時才 await（見 startRecording）。
  // 用 ref 而非 state：它的變動不該觸發重繪。
  const placeRef = useRef<Promise<ElderPlace | null> | null>(null);
  // 手勢狀態機：判定「按住說話」與「短按切換」該開錄或停錄（見 lib/talkGesture.ts）。
  // 不用 avatar state 判斷手勢——短按時 pressOut 比重繪先到，讀 state 會拿到過期值。
  const gestureRef = useRef(createTalkGesture());
  // 這一輪開錄流程的 promise：停止前先 await，消除「pressOut 跑在 record() 完成前」的競態。
  const startPromiseRef = useRef<Promise<boolean>>(Promise.resolve(false));
  // 對講機長連線（spec 2026-07-28）：後端在模型決定要查東西時會先送一則安撫話，
  // 答案好了再送第二則。連不上時 stopAndSend 自動退回 POST /turns（降級路徑仍在）。
  const socketRef = useRef<ReturnType<typeof createTalkSocket> | null>(null);
  const socketOpenRef = useRef(false);
  // 播放佇列：一輪會有兩則語音（安撫話、答案），長輩連問兩件事時還會交錯回來。
  // 聲音是線性的，同時播長輩什麼都聽不懂——故一次只播一則、先到先播。
  const playQueueRef = useRef<ReturnType<typeof createPlaybackQueue> | null>(null);
  // 共用播放器也負責 POST 回覆與後續分段；記住是否正由 WebSocket 佇列播放，
  // 才不會共用 didJustFinish 監聽把安撫語音誤判成整輪回答結束。
  const socketPlaybackRef = useRef<PlaybackItem | null>(null);
  const playbackTurnRef = useRef(new WeakMap<PlaybackItem, string>());
  const turnDraftsRef = useRef(new Map<string, TurnDraft>());
  const latestReplyTurnRef = useRef<string | null>(null);
  const postPlaybackTurnRef = useRef<string | null>(null);
  const postSequenceRef = useRef(0);
  const speechSequenceRef = useRef(0);
  const [speakingProgress] = useState(() => new Animated.Value(0));
  const [collapsedProgress] = useState(() => new Animated.Value(0));

  const { loading: sessionLoading, session, signOut, internalTesting } = useSession();

  useEffect(() => {
    Animated.timing(speakingProgress, {
      toValue: avatar === "speaking" ? 1 : 0,
      duration: motion.layout,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [avatar, speakingProgress]);

  useEffect(() => {
    Animated.timing(collapsedProgress, {
      toValue: collapsed ? 1 : 0,
      duration: motion.layout,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [collapsed, collapsedProgress]);

  function turnDraft(turnId: string): TurnDraft {
    const existing = turnDraftsRef.current.get(turnId);
    if (existing) return existing;
    const created: TurnDraft = {
      transcript: "",
      reply: "",
      pendingAudio: 0,
      finalReceived: false,
      logged: false,
    };
    turnDraftsRef.current.set(turnId, created);
    return created;
  }

  function finishTurnIfReady(turnId: string): boolean {
    const draft = turnDraftsRef.current.get(turnId);
    if (!draft || draft.logged || !draft.finalReceived || draft.pendingAudio > 0) {
      return false;
    }
    draft.logged = true;
    if (latestReplyTurnRef.current === turnId) {
      setCollapsed(true);
    }
    // 舊版伺服器若沒有 transcript 就不偽造「您說」；升級後成功回合兩欄都必定有值。
    if (draft.transcript.trim() && draft.reply.trim()) {
      void appendTurn({
        at: Date.now(),
        said: draft.transcript,
        reply: draft.reply,
      });
    }
    return true;
  }

  // 未讀提醒數（X-01）：用 useFocusEffect 而非 useEffect——從提醒頁返回時要重算，
  // 否則長輩看完提醒回來，鈴鐺上的紅點還掛著。
  useFocusEffect(
    useCallback(() => {
      if (sessionLoading || !session || session.role !== "elder") {
        return;
      }
      let alive = true;
      (async () => {
        try {
          const [items, seenAt] = await Promise.all([
            listElderNotifications(session.token),
            loadSeenAt("elder"),
          ]);
          if (alive) {
            setUnreadCount(items.filter((n) => n.created_at > seenAt).length);
          }
        } catch {
          // 提醒載入失敗時未讀數保持原值，對講機不受影響（見 unreadCount 的註解）。
        }
      })();
      return () => {
        alive = false;
      };
    }, [sessionLoading, session]),
  );

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session || session.role !== "elder") {
      router.replace("/role");
      return;
    }
    // 上一次 session 的回覆音檔殘留一次清光（C1）：cache 目錄只在裝置儲存吃緊時才被
    // 系統回收，不會每輪幫我們清。
    purgeReplyAudio();
    let alive = true;
    (async () => {
      const micPermission = await AudioModule.requestRecordingPermissionsAsync();
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      // 定位權限與麥克風一樣「開畫面就請求」：iOS 上系統權限對話框會中斷正在進行的
      // 錄音工作階段，若拖到按住說話當下才問，第一次錄音會被對話框打斷、收不到聲音。
      const locationPermission = await Location.requestForegroundPermissionsAsync();
      if (alive) {
        setMicReady(micPermission.granted);
        setLocationGranted(locationPermission.granted);
        if (!micPermission.granted) {
          setReplyText(strings.talk.micPermission);
          setAvatar("error");
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [router, sessionLoading, session]);

  // 建立長連線與播放佇列。session 換人（登出重綁）就整組重建。
  useEffect(() => {
    if (sessionLoading || !session || session.role !== "elder") {
      return;
    }
    const turnDrafts = turnDraftsRef.current;
    const failedTurnIds = new Set<string>();
    const queue = createPlaybackQueue(async (item: PlaybackItem) => {
      if (failedTurnIds.delete(item.turnId)) {
        return;
      }
      socketPlaybackRef.current = item;
      speechSequenceRef.current += 1;
      setSpeechCue({
        key: `${item.turnId}:${item.kind}:${speechSequenceRef.current}`,
        text: item.text,
        durationMs: item.durationMs,
      });
      setAvatar("speaking");
      // 等 didJustFinish 事件，時長只當保險（見 playAndWait 的 docstring）：
      // 「音檔多長」不等於「播完了」——載入、緩衝、音訊工作階段被錄音搶走都會讓
      // 實際播放時間長於時長，估短了下一則會蓋掉還在講的這一則。
      const outcome = await playAndWait(player, item).finally(() => {
        if (socketPlaybackRef.current === item) {
          socketPlaybackRef.current = null;
        }
      });
      if (outcome === "timeout") {
        // 事件沒來就靠保險放行了。留 log 而不是靜默——真的常發生的話，代表音訊
        // 工作階段有問題，那是另一個要查的東西。
        console.warn("[talk] 播放結束事件沒來，靠保險逾時放行", item.turnId);
      }
      if (failedTurnIds.delete(item.turnId)) {
        return;
      }
      const answerTurnId = playbackTurnRef.current.get(item);
      if (answerTurnId) {
        const draft = turnDraftsRef.current.get(answerTurnId);
        if (draft) {
          draft.pendingAudio = Math.max(0, draft.pendingAudio - 1);
          finishTurnIfReady(answerTurnId);
        }
      }
      const draft = turnDraftsRef.current.get(item.turnId);
      const nextState = getTalkSocketPlaybackCompletionState(
        item.kind,
        Boolean(draft && (draft.pendingAudio > 0 || !draft.finalReceived)),
      );
      if (nextState !== null) {
        // 長輩可能在播放中已開始下一輪，或同輪收到 error；只收尾本次 speaking，
        // 不覆蓋較新的 listening／thinking／error 狀態。
        setAvatar((current) => (current === "speaking" ? nextState : current));
      }
    });
    playQueueRef.current = queue;

    const socket = createTalkSocket({
      baseUrl: process.env.EXPO_PUBLIC_API_URL ?? "",
      token: session.token,
      onStatus: (status) => {
        socketOpenRef.current = status === "open";
      },
      // 內嵌音檔落地（C1）：後端把 m4a 隨 binary 訊框直接推下來，省掉「後端上傳
      // Supabase→取簽章→App 再下載」兩趟網路。socket 只負責協定，寫檔由這裡注入
      // ——見 replyAudio.ts 說明為什麼不讓 talkSocket 自己 import 檔案系統。
      writeAudio: writeReplyAudio,
      onFrame: (rawFrame: TalkFrame) => {
        // talkSocket 維持既有三態型別；後端已上線的 queued／chunk 與本批新增 transcript
        // 在呈現層做相容擴充，不去改動受測狀態機檔。
        const frame = rawFrame as RuntimeTalkFrame;
        if (frame.type === "error") {
          failedTurnIds.add(frame.turn_id);
          turnDraftsRef.current.delete(frame.turn_id);
          setReplyText(frame.text);
          setCollapsed(false);
          setAvatar("error");
          setListeningMode(null);
          return;
        }
        if (frame.type === "queued") {
          setReplyText(strings.talk.queued(frame.position));
          setCollapsed(false);
          setAvatar("thinking");
          setListeningMode(null);
          return;
        }

        if (frame.type === "reply") {
          const draft = turnDraft(frame.turn_id);
          const transcript = (frame as typeof frame & { transcript?: unknown }).transcript;
          draft.transcript = typeof transcript === "string" ? transcript : "";
          const content = applyReplyContentFrame(draft, frame);
          draft.reply = content.reply;
          draft.finalReceived = content.finalReceived;
          latestReplyTurnRef.current = frame.turn_id;
          setTranscriptText(draft.transcript);
          setReplyText(draft.reply);
          // 第一段一抵達就展開；不等後面續段合成完成。
          setCollapsed(false);
        } else if (frame.type === "chunk") {
          const draft = turnDraft(frame.turn_id);
          const content = applyReplyContentFrame(draft, frame);
          draft.reply = content.reply;
          draft.finalReceived = content.finalReceived;
          if (latestReplyTurnRef.current === frame.turn_id && frame.text) {
            setCollapsed(false);
          }
        } else {
          setReplyText(frame.text);
        }

        const playbackKind = frame.type === "ack" ? "ack" : "reply";
        // 續段失敗或根本沒有第二段時，後端會送 text=""／is_last=true 的空音檔
        // 終止訊框。它只負責結束協定，不能送進播放器，否則會平白多等一次逾時。
        const hasPlayableAudio = hasPlayableReplyAudio(frame);
        if (hasPlayableAudio) {
          const item: PlaybackItem = {
            kind: playbackKind,
            turnId: frame.turn_id,
            audioUrl: frame.audio_url,
            text:
              frame.type === "reply"
                ? firstReplyAudioText(frame.text, frame.chunk_count)
                : frame.text,
            durationMs: frame.duration_ms ?? 0,
          };
          if (playbackKind === "reply") {
            turnDraft(frame.turn_id).pendingAudio += 1;
            playbackTurnRef.current.set(item, frame.turn_id);
          }
          queue.push(item);
        } else if (frame.type === "ack" || frame.type === "reply") {
          const arrivalState = getTalkSocketFrameArrivalState(
            frame.type,
            false,
          );
          // TTS 可降級成純文字（audio_url=""）；沒有播放完成事件可收尾，需在這裡
          // 直接離開 thinking，否則長輩會永遠看到「想一下喔」且麥克風維持停用。
          if (arrivalState !== null) setAvatar(arrivalState);
        }
        const finished =
          playbackKind === "reply" ? finishTurnIfReady(frame.turn_id) : false;
        // 最後一段若是純文字或空白終止訊框，不會有播放完成事件替它收尾。
        // 只在目前沒有別輪音檔正在播時離開 speaking，避免舊輪終止訊框蓋掉新輪。
        if (finished && frame.type === "chunk" && socketPlaybackRef.current === null) {
          setAvatar((current) => (current === "speaking" ? "idle" : current));
        }
      },
    });
    socketRef.current = socket;
    return () => {
      socket.close();
      socketRef.current = null;
      playQueueRef.current = null;
      socketPlaybackRef.current = null;
      turnDrafts.clear();
      latestReplyTurnRef.current = null;
    };
    // player 在本元件生命週期內恆定，不列入相依以免重建連線。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionLoading, session]);

  /** 開始聆聽；回傳錄音是否真的開始（供 stopAndSend 與手勢復位判斷）。 */
  async function startRecording(): Promise<boolean> {
    if (!micReady || avatar === "thinking") {
      return false;
    }
    try {
      // 觸覺回饋（✅ D-48 丁-2）：長輩按住有「開始了」的體感；失敗不影響錄音。
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => undefined);
      // ⚠️ 按下去就是要講話：不清空還沒播的，阿白的聲音會被錄進去。
      playQueueRef.current?.clear();
      postPlaybackTurnRef.current = null;
      player.pause();
      // 錄音前重新宣告錄音模式：上一輪 TTS 回覆播放會把音訊工作階段留在播放類別，
      // 不重設就直接 record() 會收不到聲音（iOS AVAudioSession 類別衝突，2026-07-18 診斷）。
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      // 錄音一開始就發動取位、不 await：長輩講話的那幾秒剛好把地名反查的耗時蓋掉，送出時
      // 通常已經好了。權限已於進畫面時取得，這裡不會再跳對話框。currentPlace 永不拋，不需 catch。
      placeRef.current = currentPlace();
      setAvatar("listening");
      setListeningMode("pressing");
      setTranscriptText("");
      setCollapsed(false);
      setReplyText(strings.talk.listening);
      return true;
    } catch {
      setReplyText(strings.talk.fallback);
      setAvatar("error");
      setListeningMode(null);
      return false;
    }
  }

  async function stopAndSend() {
    // 等開錄流程完成再停：短按時 pressOut 常比 record() 先到，先前用 avatar state
    // 守門會讀到過期值而漏掉停止，造成「聆聽中」殘留、二次按壓洗掉音檔（2026-07-25 修復）。
    const started = await startPromiseRef.current;
    if (!started) {
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => undefined);
    setAvatar("thinking");
    setListeningMode(null);
    setReplyText(strings.talk.thinking);
    try {
      await recorder.stop();
      // 結束提示音在錄音停止之後才播，避免播放與錄音搶同一音訊工作階段（見 startRecording）。
      stopBeep.seekTo(0);
      stopBeep.play();
      const uri = recorder.uri;
      if (!uri) {
        throw new Error("no recording");
      }
      const place = await (placeRef.current ?? Promise.resolve(null));
      // 走長連線（spec 2026-07-28）：後端會先送一則安撫話、答案好了再送第二則，
      // 兩則都由 onFrame 接手，這裡送完就結束。連線沒開就退回 POST——降級路徑仍在，
      // 長輩不會因為網路狀況不好就完全講不了話。
      if (socketRef.current && socketOpenRef.current) {
        socketRef.current.sendLocation(place);
        socketRef.current.sendAudio(await (await fetch(uri)).arrayBuffer());
        return;
      }
      const reply = await postTurn(uri, session?.token ?? "", place);
      postSequenceRef.current += 1;
      const turnId = `post:${Date.now()}:${postSequenceRef.current}`;
      const draft = turnDraft(turnId);
      draft.transcript = reply.transcript;
      draft.reply = reply.text;
      draft.finalReceived = true;
      latestReplyTurnRef.current = turnId;
      setTranscriptText(reply.transcript);
      setReplyText(reply.text);
      setCollapsed(false);
      if (reply.audio_url) {
        draft.pendingAudio = 1;
        postPlaybackTurnRef.current = turnId;
        speechSequenceRef.current += 1;
        setSpeechCue({
          key: `post:reply:${speechSequenceRef.current}`,
          text: reply.text,
          durationMs: reply.duration_ms ?? 0,
        });
        setAvatar("speaking");
        player.replace({ uri: reply.audio_url });
        player.play();
      } else {
        setAvatar("idle");
        finishTurnIfReady(turnId);
      }
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 403) {
        setReplyText(strings.talk.bindingLost);
        await clearToday();
        await signOut();
      } else {
        setReplyText(strings.talk.fallback);
      }
      setAvatar(exc instanceof ApiError && exc.status === 403 ? "idle" : "error");
      setListeningMode(null);
    }
  }

  // 手勢接線：狀態機決定動作，這裡只負責執行對應的開錄／停錄。
  function handlePressIn() {
    const action = gestureRef.current.pressIn();
    if (action === "start") {
      startPromiseRef.current = startRecording().then((started) => {
        if (!started) {
          // 開錄失敗或被擋下：手勢復位，下一次按壓重新開始。
          gestureRef.current.reset();
          setListeningMode(null);
        }
        return started;
      });
    } else if (action === "stop") {
      void stopAndSend();
    }
  }

  function handlePressOut() {
    const action = gestureRef.current.pressOut();
    if (action === "stop") {
      void stopAndSend();
    } else if (action === "keep") {
      // 短按切換模式：維持聆聽並提示「說完再按一下」。等開錄真的成功才顯示，
      // 失敗時保留 startRecording 已顯示的錯誤訊息。
      void startPromiseRef.current.then((started) => {
        if (started) {
          setListeningMode("tap");
          setReplyText(strings.talk.listeningTapHint);
        }
      });
    }
  }

  // POST 降級路徑不分段；音檔播完即完成這輪並寫入本機今日紀錄。
  useEffect(() => {
    const sub = player.addListener("playbackStatusUpdate", (status) => {
      if (!status.didJustFinish || socketPlaybackRef.current !== null) return;
      const turnId = postPlaybackTurnRef.current;
      if (!turnId) return;
      postPlaybackTurnRef.current = null;
      const draft = turnDraftsRef.current.get(turnId);
      if (draft) draft.pendingAudio = Math.max(0, draft.pendingAudio - 1);
      finishTurnIfReady(turnId);
      setAvatar((current) => (current === "speaking" ? "idle" : current));
    });
    return () => sub.remove();
    // 回呼只讀 ref 與 player，不需要進相依陣列（進了會每次重繪都重掛監聽）。
  }, [player]);

  function confirmLogout() {
    Alert.alert(strings.talk.logoutConfirmTitle, strings.talk.logoutConfirmBody, [
      { text: strings.talk.logoutCancel, style: "cancel" },
      {
        text: strings.talk.logout,
        style: "destructive",
        onPress: async () => {
          // 先撤伺服器端 token（✅ 庚-42 長輩自助登出）；離線也不擋本機登出。
          await logoutSession(session?.token ?? "").catch(() => undefined);
          await clearToday();
          await signOut();
          router.replace("/role");
        },
      },
    ]);
  }

  const presentation = getTalkPresentation(avatar, listeningMode);
  const isSpeaking = avatar === "speaking";
  const contentScrollable = shouldScrollTalkContent(fontScale);
  const summary = collapsedReplySummary(strings.talk.collapsedPrefix, replyText);
  const contentBottom = speakingProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [226, 120],
  });
  const talkButtonSize = speakingProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [elder.talkButton, elder.talkButtonSmall],
  });
  const talkButtonRadius = speakingProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [elder.talkButton / 2, elder.talkButtonSmall / 2],
  });
  const replyCardMaxHeight = collapsedProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [contentScrollable ? Math.min(360, windowHeight * 0.44) : 280, 72],
  });
  const actionLabel = isSpeaking
    ? strings.talk.actions.waitWhileSpeaking
    : presentation.actionLabel;

  const expandedReply = (
    <>
      <View style={styles.statusRow}>
        <View
          style={[
            styles.statusIcon,
            avatar === "listening" ? styles.statusIconOnDark : null,
            avatar !== "listening"
              ? { backgroundColor: talkState[avatar].pill }
              : null,
          ]}
        >
          <TalkStatusIcon state={avatar} />
        </View>
        <Text
          selectable
          style={[styles.statusLabel, { color: talkState[avatar].ink }]}
          testID="talk-status-label"
        >
          {presentation.statusLabel}
        </Text>
      </View>
      {transcriptText ? (
        <Text selectable style={styles.saidText} testID="talk-transcript">
          {`${strings.elderHistory.youSaid}${transcriptText}`}
        </Text>
      ) : null}
      <Text
        selectable
        style={[
          styles.replyText,
          avatar === "listening" ? styles.replyTextOnDark : null,
        ]}
      >
        {transcriptText ? `${strings.elderHistory.bearSaid}${replyText}` : replyText}
      </Text>
    </>
  );

  return (
    <SafeAreaView edges={["bottom"]} style={styles.container}>
      <LinearGradient
        colors={[...elderGradient.colors]}
        locations={[...elderGradient.locations]}
        pointerEvents="none"
        style={StyleSheet.absoluteFillObject}
      />

      <View style={styles.header}>
        <Pressable
          accessibilityLabel={strings.elderHistory.entryButton}
          accessibilityRole="button"
          onPress={() => router.push("/elder/history")}
          style={({ pressed }) => [styles.roundButton, pressed ? styles.roundButtonPressed : null]}
          testID="talk-history-button"
        >
          <ChatCircleDotsIcon color={colors.primary} size={30} weight="bold" />
        </Pressable>
        <Text selectable style={styles.brand}>
          {strings.role.brand}
        </Text>
        <View style={styles.headerSpacer} />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={
            unreadCount > 0
              ? `${strings.elderNotifications.bell}，${unreadCount} 則新的`
              : strings.elderNotifications.bell
          }
          onPress={() => router.push("/elder/notifications")}
          style={({ pressed }) => [styles.roundButton, pressed ? styles.roundButtonPressed : null]}
        >
          <BellIcon color={colors.primary} size={30} />
          {unreadCount > 0 ? (
            <View style={styles.bellBadge}>
              <Text style={styles.bellBadgeText}>
                {unreadCount > 9 ? "9+" : unreadCount}
              </Text>
            </View>
          ) : null}
        </Pressable>
        <Pressable
          accessibilityLabel={strings.talk.logout}
          accessibilityRole="button"
          onPress={confirmLogout}
          style={({ pressed }) => [styles.roundButton, pressed ? styles.roundButtonPressed : null]}
        >
          <SignOutIcon color={colors.danger} size={28} weight="bold" />
        </Pressable>
      </View>

      <BearStage
        emotion={replyEmotion}
        speechCue={speechCue}
        systemState={avatar}
      />

      {internalTesting ? (
        <View style={styles.internalTesting}>
          <RoleSwitcher />
          <Text selectable style={styles.debugPermissions}>
            {`${strings.talk.debugMicLabel}：${micReady ? strings.talk.debugGranted : strings.talk.debugDenied}　${strings.talk.debugLocationLabel}：${locationGranted ? strings.talk.debugGranted : strings.talk.debugDenied}`}
          </Text>
        </View>
      ) : null}

      <Animated.View
        style={[
          styles.contentLayer,
          {
            bottom: contentBottom,
            maxHeight: contentScrollable ? Math.min(390, windowHeight * 0.48) : 370,
          },
        ]}
      >
        <Animated.View
          accessibilityLabel={`${presentation.statusLabel}。${transcriptText ? `${strings.elderHistory.youSaid}${transcriptText}。` : ""}${replyText}`}
          accessibilityLiveRegion={avatar === "error" ? "assertive" : "polite"}
          accessible
          style={[
            styles.replyCard,
            avatar === "listening" ? styles.replyCardListening : null,
            avatar === "error" ? styles.replyCardError : null,
            { maxHeight: replyCardMaxHeight },
          ]}
          testID="talk-reply-card"
        >
          <Pressable
            accessibilityHint={collapsed ? "打開完整回答" : undefined}
            accessibilityRole={collapsed ? "button" : undefined}
            disabled={!collapsed}
            onPress={() => setCollapsed(false)}
            style={styles.replyCardPressable}
          >
            {collapsed ? (
              <View style={styles.collapsedRow}>
                <ChatCircleDotsIcon color={colors.primary} size={28} weight="bold" />
                <Text numberOfLines={1} selectable style={styles.collapsedText}>
                  {summary}
                </Text>
                <CaretDownIcon color={colors.textSoft} size={26} weight="bold" />
              </View>
            ) : contentScrollable ? (
              <ScrollView
                contentContainerStyle={styles.expandedContent}
                nestedScrollEnabled
                showsVerticalScrollIndicator
                style={styles.replyScroll}
              >
                {expandedReply}
              </ScrollView>
            ) : (
              <View style={styles.expandedContent}>{expandedReply}</View>
            )}
          </Pressable>
        </Animated.View>

        {collapsed ? (
          <View
            style={[styles.statusBand, { backgroundColor: talkState[avatar].pill }]}
            testID="talk-status-band"
          >
            <View style={[styles.statusIcon, styles.statusIconCompact]}>
              <TalkStatusIcon state={avatar} />
            </View>
            <View style={styles.statusCopy}>
              <Text selectable style={[styles.statusLabel, { color: talkState[avatar].ink }]}>
                {presentation.statusLabel}
              </Text>
              <Text selectable style={[styles.statusSub, { color: talkState[avatar].ink }]}>
                {strings.talk.statusSub[avatar]}
              </Text>
            </View>
          </View>
        ) : null}
      </Animated.View>

      <View style={[styles.voiceAction, isSpeaking ? styles.voiceActionSpeaking : null]}>
        <Animated.View
          style={[
            styles.talkButtonFrame,
            {
              width: talkButtonSize,
              height: talkButtonSize,
              borderRadius: talkButtonRadius,
              backgroundColor: speakingProgress.interpolate({
                inputRange: [0, 1],
                outputRange: [colors.action, "#FDF6DE"],
              }),
            },
          ]}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={strings.talk.pressToTalk}
            accessibilityState={{
              busy: avatar === "thinking",
              disabled: !micReady || avatar === "thinking",
            }}
            onPressIn={handlePressIn}
            // 長按門檻採 Pressable 預設 delayLongPress（500ms）：達標＝按住說話、放開送出。
            onLongPress={() => {
              gestureRef.current.longPress();
              setListeningMode("hold");
            }}
            onPressOut={handlePressOut}
            disabled={!micReady || avatar === "thinking"}
            style={({ pressed }) => [
              styles.talkButton,
              pressed || avatar === "listening" ? styles.talkButtonActive : null,
              !micReady || avatar === "thinking" ? styles.talkButtonDisabled : null,
            ]}
            testID="talk-button"
          >
            <MicIcon color={isSpeaking ? colors.warningText : colors.text} size={isSpeaking ? 34 : 60} />
          </Pressable>
        </Animated.View>
        <Text
          selectable
          style={[styles.actionLabel, isSpeaking ? styles.actionLabelSpeaking : null]}
          testID="talk-action-label"
        >
          {actionLabel}
        </Text>
      </View>
    </SafeAreaView>
  );
}

function TalkStatusIcon(props: { state: TalkVisualState }) {
  const color = talkState[props.state].ink;
  const iconProps = { color, size: 32, weight: "bold" as const };
  if (props.state === "listening") {
    return <WaveformIcon {...iconProps} />;
  }
  if (props.state === "thinking") {
    return <ArrowClockwiseIcon {...iconProps} />;
  }
  if (props.state === "speaking") {
    return <SpeakerHighIcon {...iconProps} />;
  }
  if (props.state === "error") {
    return <WifiSlashIcon {...iconProps} />;
  }
  return <CheckCircleIcon {...iconProps} />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    overflow: "hidden",
  },
  header: {
    position: "absolute",
    top: 66,
    left: elder.pagePadding,
    right: elder.pagePadding,
    zIndex: 4,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  brand: {
    color: colors.primaryPressed,
    fontSize: elder.fontMin,
    fontWeight: "900",
    letterSpacing: 1.3,
    lineHeight: 28,
  },
  headerSpacer: { flex: 1 },
  roundButton: {
    width: elder.roundButton,
    height: elder.roundButton,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: elder.roundButton / 2,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: colors.primaryPressed,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 2,
  },
  roundButtonPressed: {
    transform: [{ scale: 0.98 }],
    shadowOpacity: 0.04,
  },
  bellBadge: {
    position: "absolute",
    top: 2,
    right: 2,
    minWidth: 32,
    height: 32,
    borderRadius: 16,
    paddingHorizontal: 5,
    backgroundColor: colors.dangerBadge,
    alignItems: "center",
    justifyContent: "center",
  },
  bellBadgeText: { color: "#FFFFFF", fontSize: elder.fontMin, fontWeight: "700" },
  internalTesting: {
    position: "absolute",
    top: 130,
    left: elder.pagePadding,
    right: elder.pagePadding,
    zIndex: 5,
    alignItems: "center",
    gap: spacing.xs,
  },
  debugPermissions: { fontSize: elder.fontMin, color: colors.textSoft, textAlign: "center" },
  contentLayer: {
    position: "absolute",
    left: elder.pagePadding,
    right: elder.pagePadding,
    zIndex: 2,
    gap: spacing.s,
  },
  replyCard: {
    width: "100%",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 24,
    backgroundColor: colors.surface,
    overflow: "hidden",
    shadowColor: colors.primaryPressed,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.08,
    shadowRadius: 28,
    elevation: 4,
  },
  replyCardListening: {
    borderColor: colors.primaryPressed,
    backgroundColor: talkState.listening.pill,
  },
  replyCardError: { borderColor: colors.danger },
  replyCardPressable: { width: "100%" },
  expandedContent: { padding: 18, gap: 10 },
  replyScroll: { maxHeight: 330 },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  statusIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  statusIconOnDark: { backgroundColor: "rgba(255,255,255,0.16)" },
  statusIconCompact: { backgroundColor: "transparent" },
  statusLabel: {
    flexShrink: 1,
    fontSize: 26,
    fontWeight: "900",
    lineHeight: 32,
  },
  saidText: {
    color: colors.textSoft,
    fontSize: elder.fontMin,
    fontWeight: "700",
    lineHeight: 31,
  },
  replyText: {
    color: colors.text,
    fontSize: 24,
    fontWeight: "700",
    lineHeight: 35,
  },
  replyTextOnDark: { color: "#FFFFFF" },
  collapsedRow: {
    minHeight: 70,
    paddingHorizontal: 18,
    shadowColor: colors.primaryPressed,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  collapsedText: {
    flex: 1,
    color: colors.text,
    fontSize: elder.fontMin,
    fontWeight: "700",
    lineHeight: 31,
  },
  statusBand: {
    minHeight: 76,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 24,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  statusCopy: { flex: 1 },
  statusSub: {
    flex: 1,
    fontSize: elder.fontMin,
    fontWeight: "700",
    lineHeight: 29,
  },
  voiceAction: {
    position: "absolute",
    left: elder.pagePadding,
    right: elder.pagePadding,
    bottom: 40,
    zIndex: 3,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  voiceActionSpeaking: { flexDirection: "row", gap: 14 },
  talkButtonFrame: {
    flexShrink: 0,
    shadowColor: "#D6A820",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.28,
    shadowRadius: 20,
    elevation: 5,
    overflow: "hidden",
  },
  talkButton: {
    width: "100%",
    height: "100%",
    borderWidth: 0,
    borderRadius: 999,
    backgroundColor: "transparent",
    alignItems: "center",
    justifyContent: "center",
  },
  talkButtonActive: {
    backgroundColor: "rgba(243,212,95,0.55)",
    transform: [{ scale: 0.98 }],
  },
  talkButtonDisabled: { opacity: 0.7 },
  actionLabel: {
    maxWidth: 330,
    color: colors.text,
    fontSize: 26,
    fontWeight: "900",
    letterSpacing: 0.65,
    lineHeight: 31,
    textAlign: "center",
  },
  actionLabelSpeaking: {
    maxWidth: 220,
    color: colors.textSoft,
    fontSize: elder.fontMin,
    lineHeight: 30,
    textAlign: "left",
  },
});
