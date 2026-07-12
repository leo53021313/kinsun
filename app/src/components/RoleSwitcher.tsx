import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text } from "react-native";

import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

/**
 * 內測專用（spec 2026-07-12 §3.2）：一鍵切換長輩／家屬身分。
 * 僅在伺服器 INTERNAL_TESTING_ENABLED（meta 下發）時顯示；正式環境不出現。
 * 對方身分已登入→直接切換；未登入→導向該端登入／綁定頁。
 */
export function RoleSwitcher() {
  const router = useRouter();
  const { session, otherSession, internalTesting, switchTo } = useSession();
  if (!internalTesting || !session) {
    return null;
  }
  const target = session.role === "guardian" ? "elder" : "guardian";
  const label = target === "elder" ? strings.role.switchToElder : strings.role.switchToGuardian;

  async function onPress() {
    if (otherSession) {
      await switchTo(target);
      router.replace(target === "elder" ? "/elder/talk" : "/guardian/home");
    } else {
      router.push(target === "elder" ? "/elder/bind" : "/guardian/login");
    }
  }

  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.button}>
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    alignSelf: "center",
    paddingVertical: spacing.s,
    paddingHorizontal: spacing.m,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  label: { fontSize: 14, color: colors.textSoft, fontWeight: "600" },
});
