import { useRouter } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { Button } from "@/components/ui";
import { colors, elder, spacing } from "@/lib/theme";

/** 首次開啟：選擇身分。長輩按鈕放大、置頂。 */
export default function RoleScreen() {
  const router = useRouter();
  return (
    <View style={styles.container}>
      <Text style={styles.brand}>金孫</Text>
      <Text style={styles.slogan}>聽懂國台語的長輩陪伴守護</Text>
      <View style={styles.buttons}>
        <Button
          label="我是長輩"
          size="big"
          onPress={() => router.push("/elder/bind")}
        />
        <Button
          label="我是家屬"
          variant="outline"
          onPress={() => router.push("/guardian/login")}
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
  slogan: { fontSize: 18, color: colors.textSoft, textAlign: "center" },
  buttons: { marginTop: spacing.xl, gap: spacing.l },
});
