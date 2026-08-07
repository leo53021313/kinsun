/** 阿白的固定角色舞台。
 *
 * 系統態只控制光暈與五態；回應情緒只送進角色 renderer，不得反過來改狀態帶。
 * 舞台固定 209 × 300、top 140，內容再多也不縮放或位移。
 */

import { Image } from "expo-image";
import { StyleSheet, View } from "react-native";

import { OttoBearRenderer } from "@/components/OttoBearRenderer";
import type { OttoSpeechCue } from "@/lib/ottoBridge";
import { avatar, emotionPolicy, talkState } from "@/lib/theme";
import type { TalkVisualState } from "@/lib/talkPresentation";

export type BearSystemState = TalkVisualState;
export type BearEmotion = string;

/** 本地最後一道防線；即使上游挑到黑名單情緒，也不讓角色對長輩呈現。 */
export function sanitizeEmotion(emotion: string | null | undefined): string | null {
  if (!emotion) return null;
  return (emotionPolicy.blocked as readonly string[]).includes(emotion) ? null : emotion;
}

export function bearSpeechCue(
  systemState: BearSystemState,
  emotion: string | null | undefined,
  speechCue: OttoSpeechCue | null,
): OttoSpeechCue | null {
  if (systemState !== "speaking" || !speechCue) return speechCue;
  return { ...speechCue, emotion: sanitizeEmotion(emotion) };
}

export function BearStage(props: {
  systemState: BearSystemState;
  /** 回應情緒只在 speaking 態生效；目前後端尚未回傳時傳 null。 */
  emotion?: string | null;
  speechCue?: OttoSpeechCue | null;
}) {
  const { systemState } = props;
  const speechCue = bearSpeechCue(systemState, props.emotion, props.speechCue ?? null);

  return (
    <View pointerEvents="none" style={styles.stage} testID="bear-stage">
      <View
        style={[styles.glow, { backgroundColor: talkState[systemState].glow }]}
        testID="bear-stage-glow"
      />
      <View
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={[styles.bear, systemState === "error" ? styles.bearDimmed : null]}
      >
        <OttoBearRenderer state={systemState} speechCue={speechCue} />
      </View>
    </View>
  );
}

/** 清單頁的小頭像；正式五態 PNG 尚未交付，先沿用已納入的阿白靜態 fallback。 */
export function BearAvatar(props: { systemState?: BearSystemState }) {
  const state = props.systemState ?? "idle";
  return (
    <View style={styles.headerAvatar}>
      <View style={[styles.headerGlow, { backgroundColor: talkState[state].glow }]} />
      <Image
        accessibilityElementsHidden
        contentFit="contain"
        importantForAccessibility="no-hide-descendants"
        source={require("@/assets/images/akin-hero.png")}
        style={styles.headerImage}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    position: "absolute",
    top: avatar.stageTop,
    left: "50%",
    marginLeft: -(avatar.stageW / 2),
    width: avatar.stageW,
    height: avatar.stageH,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1,
  },
  // RN 沒有 radial-gradient；正式漸層素材交付前，以低透明度圓角色塊近似。
  glow: {
    position: "absolute",
    left: -26,
    right: -26,
    top: -26,
    bottom: -26,
    borderRadius: 48,
    opacity: 0.9,
  },
  bear: { width: "100%", height: "100%" },
  bearDimmed: { opacity: avatar.dimmedOpacity },
  headerAvatar: {
    width: avatar.headerW,
    height: avatar.headerH,
    alignItems: "center",
    justifyContent: "center",
  },
  headerGlow: {
    position: "absolute",
    left: -6,
    right: -6,
    top: -4,
    bottom: -4,
    borderRadius: 14,
  },
  headerImage: { width: "100%", height: "100%" },
});
