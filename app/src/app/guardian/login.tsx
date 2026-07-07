import { Link, useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";

import { Button, ErrorText, Field } from "@/components/ui";
import { ApiError, loginGuardian } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { colors, spacing } from "@/lib/theme";

export default function GuardianLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    setBusy(true);
    try {
      const session = await loginGuardian(email, password);
      await saveSession({ role: "guardian", token: session.token, display_name: session.name });
      router.replace("/guardian/home");
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 401) {
        setError("帳號或密碼不對，請再試一次。");
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
        <Field
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="you@example.com"
        />
        <Field
          label="密碼"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholder="至少 8 碼"
        />
        <ErrorText message={error} />
        <Button label="登入" onPress={submit} busy={busy} />
        <Link href="/guardian/register" style={styles.link}>
          <Text style={styles.linkText}>還沒有帳號？註冊</Text>
        </Link>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  form: { padding: spacing.l, gap: spacing.m },
  link: { alignSelf: "center", marginTop: spacing.s },
  linkText: { color: colors.primary, fontSize: 16, fontWeight: "600" },
});
