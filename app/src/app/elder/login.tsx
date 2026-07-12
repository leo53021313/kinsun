import { useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";

import { Button, ErrorText, Field } from "@/components/ui";
import { ApiError, loginElder } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import { colors, spacing } from "@/lib/theme";

/** 長輩帳密登入（✅ D-71 己-6）：只管「重登」（換手機／登出後）；
 * 首次使用仍要掃家人給的 QR 完成配對。字級放大、訊息白話。 */
export default function ElderLogin() {
  const router = useRouter();
  const { signIn } = useSession();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    setBusy(true);
    try {
      const session = await loginElder(phone, password);
      await signIn({ role: "elder", token: session.token, display_name: session.name });
      router.replace("/elder/talk");
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 403) {
        setError("這支手機還沒跟家人配對過，請先請家人給您綁定圖（QR）掃描一次。");
      } else if (exc instanceof ApiError && exc.status === 401) {
        setError("號碼或密碼不對，可以請家人幫忙確認。");
      } else {
        setError(exc instanceof Error ? exc.message : "連線失敗，請稍後再試。");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.form}>
        <Text style={styles.hint} maxFontSizeMultiplier={1.4}>
          輸入家人幫您設定的手機號碼和密碼，登入一次就會一直記住。
        </Text>
        <Field
          label="手機號碼"
          value={phone}
          onChangeText={setPhone}
          keyboardType="phone-pad"
          placeholder="09xxxxxxxx"
        />
        <Field label="密碼" value={password} onChangeText={setPassword} secureTextEntry />
        <ErrorText message={error} />
        <Button label="登入" onPress={submit} busy={busy} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  form: { padding: spacing.l, gap: spacing.m },
  hint: { fontSize: 18, color: colors.textSoft, lineHeight: 26 },
});
