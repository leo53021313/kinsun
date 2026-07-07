/** 虛擬形象預留區：MVP 以表情符號＋狀態樣式呈現；日後換 Rive／Live2D 不動版面。 */

import { StyleSheet, Text, View } from "react-native";

import { colors } from "@/lib/theme";

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

const FACES: Record<AvatarState, string> = {
  idle: "😊",
  listening: "👂",
  thinking: "🤔",
  speaking: "😄",
};

export function AvatarPlaceholder(props: { state: AvatarState }) {
  return (
    <View style={[styles.circle, props.state === "listening" ? styles.circleActive : null]}>
      <Text style={styles.face}>{FACES[props.state]}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  circle: {
    width: 180,
    height: 180,
    borderRadius: 90,
    backgroundColor: colors.surface,
    borderWidth: 3,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  circleActive: { borderColor: colors.primary },
  face: { fontSize: 96 },
});
