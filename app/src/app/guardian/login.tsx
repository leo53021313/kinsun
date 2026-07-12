import { Link, useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";

import { Button, ErrorText, Field } from "@/components/ui";
import { ApiError, loginGuardian } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

export default function GuardianLogin() {
  const router = useRouter();
  const { signIn } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    setBusy(true);
    try {
      const session = await loginGuardian(email, password);
      await signIn({ role: "guardian", token: session.token, display_name: session.name });
      router.replace("/guardian/home");
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 401) {
        setError(strings.guardianLogin.wrongCredentials);
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
        <Button label={strings.common.login} onPress={submit} busy={busy} />
        <Link href="/guardian/register" style={styles.link}>
          <Text style={styles.linkText}>{strings.guardianLogin.registerLink}</Text>
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
