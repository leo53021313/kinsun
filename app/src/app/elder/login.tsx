import { useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";

import { Button, ErrorText, Field } from "@/components/ui";
import { ApiError, loginElder } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
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
        setError(strings.elderLogin.notPaired);
      } else if (exc instanceof ApiError && exc.status === 401) {
        setError(strings.elderLogin.wrongCredentials);
      } else {
        setError(exc instanceof Error ? exc.message : strings.common.connectionFailed);
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
          {strings.elderLogin.hint}
        </Text>
        <Field
          label={strings.elderLogin.phoneLabel}
          value={phone}
          onChangeText={setPhone}
          keyboardType="phone-pad"
          placeholder="09xxxxxxxx"
        />
        <Field label={strings.common.passwordLabel} value={password} onChangeText={setPassword} secureTextEntry />
        <ErrorText message={error} />
        <Button label={strings.common.login} onPress={submit} busy={busy} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  form: { padding: spacing.l, gap: spacing.m },
  hint: { fontSize: 18, color: colors.textSoft, lineHeight: 26 },
});
