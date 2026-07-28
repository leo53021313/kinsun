import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioRecorder,
} from "expo-audio";
import { useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import * as Haptics from "expo-haptics";
import * as Location from "expo-location";
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AvatarPlaceholder, type AvatarState } from "@/components/AvatarPlaceholder";
import { MicIcon } from "@/components/MicIcon";
import { RoleSwitcher } from "@/components/RoleSwitcher";
import { ApiError, getTurnChunk, logoutSession, postTurn } from "@/lib/api";
import type { TurnChunk } from "@/lib/api";
import { type ElderPlace, currentPlace } from "@/lib/location";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { createTalkGesture } from "@/lib/talkGesture";
import {
  createPlaybackQueue,
  createTalkSocket,
  playAndWait,
  type PlaybackItem,
  type TalkFrame,
} from "@/lib/talkSocket";
import { colors, elder, spacing } from "@/lib/theme";

/**
 * 分段播放的進度（2026-07-26 延遲優化）。
 *
 * 伺服器只先合成回覆的第一句就送出（TTS 是 0.9 秒固定成本＋每字 0.10 秒，整段合成
 * 完才送會讓長輩等 5～8 秒），其餘由這裡逐段取來接著播。`digest` 綁定是哪一輪的
 * 回覆——長輩若在播放中又講了一句，伺服器會回 409，續播就此停止。
 */
type ChunkQueue = {
  digest: string;
  token: string;
  total: number;
  /** 下一個「要去取」的段號（第 0 段已隨回合回應拿到）。 */
  nextIndex: number;
  /** 已在背景取的下一段；一邊播這段、一邊取下一段，才不會段與段之間卡住。 */
  pending: Promise<TurnChunk | null> | null;
};

/**
 * 對講機：兩種說話方式（2026-07-25）→ 金孫回覆（文字放大＋自動播放語音）。
 * - 按住說話：按住聆聽、放開送出。
 * - 短按切換：按一下開始聆聽、說完再按一下送出。
 */
export default function ElderTalk() {
  const router = useRouter();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const player = useAudioPlayer();
  // 結束提示音（✅ D-48 丁-2）：放開後播一聲確認「送出了」。起始不再播提示音——iOS 上
  // 播放會把音訊工作階段切到播放類別、與錄音相衝，導致錄音在約 0.6 秒被靜默中斷
  // （2026-07-18 診斷），起始改以觸覺＋畫面提示代替。
  const stopBeep = useAudioPlayer(require("@/assets/sounds/record-stop.wav"));
  const [avatar, setAvatar] = useState<AvatarState>("idle");
  const [replyText, setReplyText] = useState<string>(strings.talk.idleHint);
  const [micReady, setMicReady] = useState(false);
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
  // 分段播放佇列（2026-07-26 延遲優化）：伺服器只先合成第一句就送出，其餘逐段取。
  // 用 ref 而非 state——它的變動不該觸發重繪，而且 playbackStatusUpdate 的回呼要讀到
  // 最新值（state 會被閉包鎖在註冊當下的那一版）。
  const queueRef = useRef<ChunkQueue | null>(null);
  // 對講機長連線（spec 2026-07-28）：後端在模型決定要查東西時會先送一則安撫話，
  // 答案好了再送第二則。連不上時 stopAndSend 自動退回 POST /turns（降級路徑仍在）。
  const socketRef = useRef<ReturnType<typeof createTalkSocket> | null>(null);
  const socketOpenRef = useRef(false);
  // 播放佇列：一輪會有兩則語音（安撫話、答案），長輩連問兩件事時還會交錯回來。
  // 聲音是線性的，同時播長輩什麼都聽不懂——故一次只播一則、先到先播。
  const playQueueRef = useRef<ReturnType<typeof createPlaybackQueue> | null>(null);

  const { loading: sessionLoading, session, signOut, internalTesting } = useSession();

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session || session.role !== "elder") {
      router.replace("/role");
      return;
    }
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
    const queue = createPlaybackQueue(async (item: PlaybackItem) => {
      setAvatar("speaking");
      // 等 didJustFinish 事件，時長只當保險（見 playAndWait 的 docstring）：
      // 「音檔多長」不等於「播完了」——載入、緩衝、音訊工作階段被錄音搶走都會讓
      // 實際播放時間長於時長，估短了下一則會蓋掉還在講的這一則。
      const outcome = await playAndWait(player, item);
      if (outcome === "timeout") {
        // 事件沒來就靠保險放行了。留 log 而不是靜默——真的常發生的話，代表音訊
        // 工作階段有問題，那是另一個要查的東西。
        console.warn("[talk] 播放結束事件沒來，靠保險逾時放行", item.turnId);
      }
    });
    playQueueRef.current = queue;

    const socket = createTalkSocket({
      baseUrl: process.env.EXPO_PUBLIC_API_URL ?? "",
      token: session.token,
      onStatus: (status) => {
        socketOpenRef.current = status === "open";
      },
      onFrame: (frame: TalkFrame) => {
        if (frame.type === "error") {
          setReplyText(frame.text);
          setAvatar("idle");
          return;
        }
        setReplyText(frame.text);
        if (frame.type === "reply") {
          // 上一輪的續播就此作廢（同 POST 路徑的處理）。
          queueRef.current = null;
          if (frame.chunk_count > 1 && frame.reply_digest) {
            const chunks: ChunkQueue = {
              digest: frame.reply_digest,
              token: session.token,
              total: frame.chunk_count,
              nextIndex: 1,
              pending: null,
            };
            queueRef.current = chunks;
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
        }
      },
    });
    socketRef.current = socket;
    return () => {
      socket.close();
      socketRef.current = null;
      playQueueRef.current = null;
    };
    // player 與 prefetchNext 在本元件生命週期內恆定，不列入相依以免重建連線。
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
      // ⚠️ 按下去就是要講話：不清空還沒播的，金孫的聲音會被錄進去。
      playQueueRef.current?.clear();
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
      setReplyText(strings.talk.listening);
      return true;
    } catch {
      setReplyText(strings.talk.fallback);
      setAvatar("idle");
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
      setReplyText(reply.text);
      // 上一輪的續播就此作廢：advanceQueue 以物件識別比對，舊佇列的取回會自行退場。
      queueRef.current = null;
      if (reply.audio_url) {
        setAvatar("speaking");
        if (reply.chunk_count > 1 && reply.reply_digest) {
          const queue: ChunkQueue = {
            digest: reply.reply_digest,
            token: session?.token ?? "",
            total: reply.chunk_count,
            nextIndex: 1,
            pending: null,
          };
          queueRef.current = queue;
          // 第一段還在播的時候就去取第二段——不先取，段與段之間會空掉一整個合成的時間。
          prefetchNext(queue);
        }
        player.replace({ uri: reply.audio_url });
        player.play();
      } else {
        setAvatar("idle");
      }
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 403) {
        setReplyText(strings.talk.bindingLost);
        await signOut();
      } else {
        setReplyText(strings.talk.fallback);
      }
      setAvatar("idle");
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
          setReplyText(strings.talk.listeningTapHint);
        }
      });
    }
  }

  /** 背景取下一段；取不到（409／網路／合成失敗）就記成 null，播完這段即收工。 */
  function prefetchNext(queue: ChunkQueue) {
    if (queue.nextIndex >= queue.total) {
      queue.pending = null;
      return;
    }
    const index = queue.nextIndex;
    queue.nextIndex += 1;
    queue.pending = getTurnChunk(index, queue.digest, queue.token).catch(() => null);
  }

  /** 這一段播完了：接上已在背景取好的下一段；沒有下一段就回到待機。 */
  async function advanceQueue() {
    const queue = queueRef.current;
    if (!queue?.pending) {
      queueRef.current = null;
      setAvatar("idle");
      return;
    }
    const chunk = await queue.pending;
    // 等待期間長輩又講了一句：這一輪已作廢，交給新的那一輪，不可以插播。
    if (queueRef.current !== queue) {
      return;
    }
    if (!chunk?.audio_url) {
      queueRef.current = null;
      setAvatar("idle");
      return;
    }
    prefetchNext(queue);
    player.replace({ uri: chunk.audio_url });
    player.play();
  }

  // 一段播完就接下一段；沒有下一段才回到待機表情。
  useEffect(() => {
    const sub = player.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) {
        void advanceQueue();
      }
    });
    return () => sub.remove();
    // advanceQueue 只讀 ref 與 player，不需要進相依陣列（進了會每次重繪都重掛監聽）。
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          await signOut();
          router.replace("/role");
        },
      },
    ]);
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topRow}>
        <RoleSwitcher />
        <Pressable accessibilityRole="button" onPress={confirmLogout} style={styles.logoutButton}>
          <Text style={styles.logoutText} maxFontSizeMultiplier={1.6}>
            {strings.talk.logout}
          </Text>
        </Pressable>
      </View>
      {internalTesting ? (
        <Text style={styles.debugPermissions} maxFontSizeMultiplier={1.2}>
          {`${strings.talk.debugMicLabel}：${micReady ? strings.talk.debugGranted : strings.talk.debugDenied}　${strings.talk.debugLocationLabel}：${locationGranted ? strings.talk.debugGranted : strings.talk.debugDenied}`}
        </Text>
      ) : null}
      <View style={styles.avatarZone}>
        <AvatarPlaceholder state={avatar} />
      </View>
      <ScrollView
        style={styles.replyZone}
        contentContainerStyle={styles.replyContent}
        showsVerticalScrollIndicator
      >
        <Text style={styles.replyText} maxFontSizeMultiplier={2}>
          {replyText}
        </Text>
      </ScrollView>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={strings.talk.pressToTalk}
        onPressIn={handlePressIn}
        // 長按門檻採 Pressable 預設 delayLongPress（500ms）：達標＝按住說話、放開送出。
        onLongPress={() => gestureRef.current.longPress()}
        onPressOut={handlePressOut}
        disabled={!micReady || avatar === "thinking"}
        style={({ pressed }) => [
          styles.talkButton,
          pressed || avatar === "listening" ? styles.talkButtonActive : null,
          !micReady || avatar === "thinking" ? styles.talkButtonDisabled : null,
        ]}
      >
        <MicIcon size={52} />
      </Pressable>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    padding: spacing.l,
    gap: spacing.l,
  },
  topRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  debugPermissions: { fontSize: 13, color: colors.textSoft, textAlign: "center" },
  logoutButton: { paddingVertical: 8, paddingHorizontal: spacing.m, minHeight: 48, justifyContent: "center" },
  logoutText: { fontSize: 16, color: colors.textSoft },
  avatarZone: { alignItems: "center", marginTop: spacing.xl },
  // 回覆改可捲動（2026-07-18）：短回覆置中、長回覆或大系統字級可上滑看完整，字級不縮。
  replyZone: { flex: 1 },
  replyContent: { flexGrow: 1, justifyContent: "center", paddingVertical: spacing.s },
  replyText: {
    fontSize: elder.fontBig,
    lineHeight: elder.fontBig * 1.4,
    color: colors.text,
    textAlign: "center",
    fontWeight: "600",
  },
  // 圓形麥克風主鍵（2026-07-18）：取代整條大按鈕，讓出垂直空間給回覆；仍是超大觸控目標。
  talkButton: {
    width: 104,
    height: 104,
    borderRadius: 52,
    backgroundColor: colors.primary,
    alignSelf: "center",
    alignItems: "center",
    justifyContent: "center",
  },
  talkButtonActive: { backgroundColor: colors.primaryPressed },
  talkButtonDisabled: { opacity: 0.5 },
});
