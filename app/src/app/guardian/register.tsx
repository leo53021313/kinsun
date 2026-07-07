import { useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, View } from "react-native";

import { Button, ErrorText, Field } from "@/components/ui";
import { ApiError, registerGuardian } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { colors, spacing } from "@/lib/theme";

export default function GuardianRegister() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    if (password.length < 8) {
      setError("密碼至少 8 碼。");
      return;
    }
    setBusy(true);
    try {
      const session = await registerGuardian(email, password, name.trim());
      await saveSession({ role: "guardian", token: session.token, display_name: session.name });
      router.replace("/guardian/home");
    } catch (exc) {
      if (exc instanceof ApiError && exc.detail === "email_taken") {
        setError("這個 Email 已經註冊過了，請直接登入。");
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
        <Field label="您的稱呼" value={name} onChangeText={setName} placeholder="例如：兒子小明" />
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
        <Button label="註冊並登入" onPress={submit} busy={busy} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  form: { padding: spacing.l, gap: spacing.m },
});
