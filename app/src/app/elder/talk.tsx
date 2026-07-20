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
import { ApiError, logoutSession, postTurn } from "@/lib/api";
import { type ElderPlace, currentPlace } from "@/lib/location";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, elder, spacing } from "@/lib/theme";

/** 對講機：按住說話 → 放開送出 → 金孫回覆（文字放大＋自動播放語音）。 */
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

  async function startRecording() {
    if (!micReady || avatar === "thinking") {
      return;
    }
    try {
      // 觸覺回饋（✅ D-48 丁-2）：長輩按住有「開始了」的體感；失敗不影響錄音。
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => undefined);
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
    } catch {
      setReplyText(strings.talk.fallback);
      setAvatar("idle");
    }
  }

  async function stopAndSend() {
    if (avatar !== "listening") {
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
      const reply = await postTurn(uri, session?.token ?? "", place);
      setReplyText(reply.text);
      if (reply.audio_url) {
        setAvatar("speaking");
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

  // 播放結束回到待機表情。
  useEffect(() => {
    const sub = player.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) {
        setAvatar("idle");
      }
    });
    return () => sub.remove();
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
        onPressIn={startRecording}
        onPressOut={stopAndSend}
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
