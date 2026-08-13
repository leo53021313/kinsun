/** 角色舞台（原 AvatarPlaceholder）。
 *
 * 2026-08 改版重點：
 *   - 舞台 209 × 300 直式，位置固定在 top 140，**永不縮放或位移**。
 *     需要空間時讓位的是麥克風主鍵與回話卡，不是角色。
 *   - 兩層情緒：systemState 驅動光暈；emotion 只換角色本身。
 *   - 素材 684 × 980（1 : 1.433），透明背景，四邊各留 8% 透明邊。
 *
 * 命名刻意中性（Bear 而非 AKin／Bai）——角色日後再改名不必動元件。
 */

import { Image, StyleSheet, View } from "react-native";

import { avatar, emotionPolicy, talkState } from "@/lib/theme";
import type { TalkVisualState } from "@/lib/talkPresentation";

export type BearSystemState = TalkVisualState;

/** 回應情緒的 key（對映 pet-core/emotions.js 的 registry）。 */
export type BearEmotion = string;

/** 五個系統態各一份素材。speaking 之後會換成可對嘴的向量版。 */
const SOURCES: Record<BearSystemState, ReturnType<typeof require>> = {
  idle: require("@/assets/images/bear/idle.png"),
  listening: require("@/assets/images/bear/listening.png"),
  thinking: require("@/assets/images/bear/thinking.png"),
  speaking: require("@/assets/images/bear/speaking.png"),
  error: require("@/assets/images/bear/error.png"),
};

/** 回應情緒的素材。缺的 key 會 fallback 到系統態的圖，不會壞畫面。 */
const EMOTION_SOURCES: Record<string, ReturnType<typeof require>> = {
  // 先放常用的三類；其餘由 LLM 挑到時再補素材
  celebrating: require("@/assets/images/bear/emo-celebrating.png"),
  touched: require("@/assets/images/bear/emo-touched.png"),
  proud: require("@/assets/images/bear/emo-proud.png"),
  hurt: require("@/assets/images/bear/emo-hurt.png"),
  apologetic: require("@/assets/images/bear/emo-apologetic.png"),
  lonely: require("@/assets/images/bear/emo-lonely.png"),
  love: require("@/assets/images/bear/emo-love.png"),
};

/** 黑名單擋在最後一關：LLM 與 sentiment.js 的本地比對都可能挑到這些。 */
export function sanitizeEmotion(emotion: string | null | undefined): string | null {
  if (!emotion) return null;
  if ((emotionPolicy.blocked as readonly string[]).includes(emotion)) return null;
  return emotion;
}

export function BearStage(props: {
  systemState: BearSystemState;
  /** LLM 挑的回應情緒；只在 speaking 態生效，其餘忽略。 */
  emotion?: string | null;
}) {
  const { systemState } = props;
  const emotion = systemState === "speaking" ? sanitizeEmotion(props.emotion) : null;
  const source = (emotion && EMOTION_SOURCES[emotion]) || SOURCES[systemState];
  const glow = talkState[systemState].glow;

  return (
    <View style={styles.stage} pointerEvents="none">
      {/* 光暈永遠跟著系統態走——阿白在 celebrating 也一樣，只要 speaking 就是綠光暈 */}
      <View style={[styles.glow, { backgroundColor: glow }]} />
      <Image
        source={source}
        resizeMode="contain"
        accessibilityIgnoresInvertColors
        // 狀態語意由狀態帶的文字＋圖示承擔，角色不需要可存取名稱
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={[
          styles.image,
          systemState === "error" ? { opacity: avatar.dimmedOpacity } : null,
        ]}
      />
    </View>
  );
}

/** 頁首小頭像：清單頁沒有舞台時用。34 × 48，同一組素材縮小。 */
export function BearAvatar(props: { systemState?: BearSystemState }) {
  const state = props.systemState ?? "idle";
  return (
    <View style={styles.headerAvatar}>
      <View style={[styles.headerGlow, { backgroundColor: talkState[state].glow }]} />
      <Image
        source={SOURCES[state]}
        resizeMode="contain"
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={styles.headerImage}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    position: "absolute",
    top: avatar.stageTop,
    alignSelf: "center",
    width: avatar.stageW,
    height: avatar.stageH,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1,
  },
  // RN 沒有 radial-gradient；用大圓角＋低透明度色塊近似。
  // 要更接近設計稿可換 expo-linear-gradient 的 RadialGradient 或一張漸層 PNG。
  glow: {
    position: "absolute",
    left: -12,
    right: -12,
    top: -12,
    bottom: -12,
    borderRadius: 999,
    opacity: 0.9,
  },
  image: { width: "100%", height: "100%" },
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
