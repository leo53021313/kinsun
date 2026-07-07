import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioRecorder,
} from "expo-audio";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AvatarPlaceholder, type AvatarState } from "@/components/AvatarPlaceholder";
import { ApiError, postTurn } from "@/lib/api";
import { clearSession, loadSession } from "@/lib/auth";
import { colors, elder, spacing } from "@/lib/theme";

const IDLE_HINT = "按住下面的大按鈕，跟金孫說話";
const FALLBACK_TEXT = "金孫沒聽清楚，再說一次好嗎？";

/** 對講機：按住說話 → 放開送出 → 金孫回覆（文字放大＋自動播放語音）。 */
export default function ElderTalk() {
  const router = useRouter();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const player = useAudioPlayer();
  const [token, setToken] = useState("");
  const [avatar, setAvatar] = useState<AvatarState>("idle");
  const [replyText, setReplyText] = useState(IDLE_HINT);
  const [micReady, setMicReady] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      const session = await loadSession();
      if (!session || session.role !== "elder") {
        router.replace("/role");
        return;
      }
      if (alive) {
        setToken(session.token);
      }
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      if (alive) {
        setMicReady(permission.granted);
        if (!permission.granted) {
          setReplyText("需要麥克風權限才能跟金孫說話，請到設定開啟。");
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [router]);

  async function startRecording() {
    if (!micReady || avatar === "thinking") {
      return;
    }
    try {
      player.pause();
      await recorder.prepareToRecordAsync();
      recorder.record();
      setAvatar("listening");
      setReplyText("金孫在聽…");
    } catch {
      setReplyText(FALLBACK_TEXT);
      setAvatar("idle");
    }
  }

  async function stopAndSend() {
    if (avatar !== "listening") {
      return;
    }
    setAvatar("thinking");
    setReplyText("金孫想一下…");
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) {
        throw new Error("no recording");
      }
      const reply = await postTurn(uri, token);
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
        setReplyText("這台手機的綁定失效了，請家人重新給您一組號碼。");
        await clearSession();
      } else {
        setReplyText(FALLBACK_TEXT);
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
      <View style={styles.avatarZone}>
        <AvatarPlaceholder state={avatar} />
      </View>
      <View style={styles.replyZone}>
        <Text style={styles.replyText}>{replyText}</Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="按住說話"
        onPressIn={startRecording}
        onPressOut={stopAndSend}
        disabled={!micReady || avatar === "thinking"}
        style={({ pressed }) => [
          styles.talkButton,
          pressed ? styles.talkButtonActive : null,
          !micReady || avatar === "thinking" ? styles.talkButtonDisabled : null,
        ]}
      >
        <Text style={styles.talkLabel}>
          {avatar === "listening" ? "放開就送出" : "按住說話"}
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
