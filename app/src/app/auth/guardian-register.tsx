import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, View } from "react-native";

import { Button, ErrorText, Field } from "@/components/ui";
import { ApiError, registerGuardian } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

export default function GuardianRegister() {
  const router = useRouter();
  const { session: activeSession, signIn } = useSession();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (activeSession?.role === "guardian") {
      router.replace("/guardian/home");
    }
  }, [activeSession?.role, router]);

  async function submit() {
    setError("");
    if (password.length < 8) {
      setError(strings.guardianRegister.passwordTooShort);
      return;
    }
    setBusy(true);
    try {
      const session = await registerGuardian(email, password, name.trim());
      await signIn({ role: "guardian", token: session.token, display_name: session.name });
    } catch (exc) {
      if (exc instanceof ApiError && exc.code === "email_taken") {
        setError(strings.guardianRegister.emailTaken);
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
        <Field
          label={strings.guardianRegister.nameLabel}
          value={name}
          onChangeText={setName}
          placeholder={strings.guardianRegister.namePlaceholder}
        />
        <Field
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="you@example.com"
        />
        <Field
          label={strings.common.passwordLabel}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholder={strings.common.passwordPlaceholder}
        />
        <ErrorText message={error} />
        <Button label={strings.guardianRegister.submit} onPress={submit} busy={busy} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  form: { padding: spacing.l, gap: spacing.m },
});
