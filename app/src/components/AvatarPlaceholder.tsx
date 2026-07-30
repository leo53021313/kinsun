/** 阿金陪伴角色：先以核准靜態插畫呈現，保留 state 介面供日後 Rive／Live2D 對嘴。 */

import { Image } from "expo-image";
import { StyleSheet, View } from "react-native";

import type { TalkVisualState } from "@/lib/talkPresentation";

export type AvatarState = TalkVisualState;

export function AvatarPlaceholder(props: { state: AvatarState }) {
  return (
    <View
      accessibilityLabel="戴著圓眼鏡與橘色領巾、微笑陪伴的阿金"
      accessibilityRole="image"
      style={styles.frame}
      testID="akin-companion"
    >
      <Image
        source={require("@/assets/images/akin-hero.png")}
        contentFit="contain"
        transition={160}
        style={[
          styles.image,
          props.state === "listening" ? styles.listening : null,
          props.state === "thinking" ? styles.thinking : null,
          props.state === "speaking" ? styles.speaking : null,
          props.state === "error" ? styles.error : null,
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    width: "100%",
    maxWidth: 285,
    aspectRatio: 1317 / 1194,
    alignSelf: "center",
  },
  image: { width: "100%", height: "100%" },
  listening: { transform: [{ scale: 1.025 }] },
  thinking: { opacity: 0.84 },
  speaking: { transform: [{ translateY: -3 }] },
  error: { opacity: 0.68 },
});
