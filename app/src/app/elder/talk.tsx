import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioRecorder,
} from "expo-audio";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import * as Haptics from "expo-haptics";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AvatarPlaceholder, type AvatarState } from "@/components/AvatarPlaceholder";
import { RoleSwitcher } from "@/components/RoleSwitcher";
import { ApiError, postTurn } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, elder, spacing } from "@/lib/theme";

/** 對講機：按住說話 → 放開送出 → 金孫回覆（文字放大＋自動播放語音）。 */
export default function ElderTalk() {
  const router = useRouter();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const player = useAudioPlayer();
  // 錄音提示音（✅ D-48 丁-2）：開始／結束各一聲，跟觸覺一起給體感。
  const startBeep = useAudioPlayer(require("@/assets/sounds/record-start.wav"));
  const stopBeep = useAudioPlayer(require("@/assets/sounds/record-stop.wav"));
  const [avatar, setAvatar] = useState<AvatarState>("idle");
  const [replyText, setReplyText] = useState<string>(strings.talk.idleHint);
  const [micReady, setMicReady] = useState(false);

  const { loading: sessionLoading, session, signOut } = useSession();

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
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      if (alive) {
        setMicReady(permission.granted);
        if (!permission.granted) {
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
      startBeep.seekTo(0);
      startBeep.play();
      player.pause();
      await recorder.prepareToRecordAsync();
      recorder.record();
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
    stopBeep.seekTo(0);
    stopBeep.play();
    setAvatar("thinking");
    setReplyText(strings.talk.thinking);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) {
        throw new Error("no recording");
      }
      const reply = await postTurn(uri, session?.token ?? "");
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

  return (
    <SafeAreaView style={styles.container}>
      <RoleSwitcher />
      <View style={styles.avatarZone}>
        <AvatarPlaceholder state={avatar} />
      </View>
      <View style={styles.replyZone}>
        <Text style={styles.replyText} maxFontSizeMultiplier={2}>{replyText}</Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={strings.talk.pressToTalk}
        onPressIn={startRecording}
        onPressOut={stopAndSend}
        disabled={!micReady || avatar === "thinking"}
        style={({ pressed }) => [
          styles.talkButton,
          pressed ? styles.talkButtonActive : null,
          !micReady || avatar === "thinking" ? styles.talkButtonDisabled : null,
        ]}
      >
        <Text style={styles.talkLabel} maxFontSizeMultiplier={1.4}>
          {avatar === "listening" ? strings.talk.releaseToSend : strings.talk.pressToTalk}
        </Text>
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
  avatarZone: { alignItems: "center", marginTop: spacing.xl },
  replyZone: { flex: 1, justifyContent: "center" },
  replyText: {
    fontSize: elder.fontBig,
    lineHeight: elder.fontBig * 1.4,
    color: colors.text,
    textAlign: "center",
    fontWeight: "600",
  },
  talkButton: {
    backgroundColor: colors.primary,
    borderRadius: 28,
    paddingVertical: 48,
    alignItems: "center",
    justifyContent: "center",
  },
  talkButtonActive: { backgroundColor: colors.primaryPressed },
  talkButtonDisabled: { opacity: 0.5 },
  talkLabel: { color: "#FFFFFF", fontSize: elder.fontHuge, fontWeight: "800" },
});
