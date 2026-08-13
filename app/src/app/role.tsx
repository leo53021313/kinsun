import { useRouter } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { Button } from "@/components/ui";
import { strings } from "@/lib/strings";
import { colors, elder, spacing } from "@/lib/theme";

/** 首次開啟：選擇身分。長輩按鈕放大、置頂。 */
export default function RoleScreen() {
  const router = useRouter();
  return (
    <View style={styles.container}>
      <Text style={styles.brand}>{strings.role.brand}</Text>
      <Text style={styles.slogan}>{strings.role.slogan}</Text>
      <View style={styles.buttons}>
        <Button
          label={strings.role.iAmElder}
          size="big"
          onPress={() => router.push("/elder/bind")}
        />
        <Button
          label={strings.role.iAmGuardian}
          variant="outline"
          size="big"
          onPress={() => router.push("/auth/guardian-login")}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    padding: spacing.xl,
    justifyContent: "center",
    gap: spacing.m,
  },
  brand: {
    fontSize: elder.fontHuge + 16,
    fontWeight: "800",
    color: colors.primary,
    textAlign: "center",
  },
  slogan: { fontSize: elder.fontMin, color: colors.textSoft, textAlign: "center" },
  buttons: { marginTop: spacing.xl, gap: spacing.l },
});
