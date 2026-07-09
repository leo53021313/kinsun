import { useRouter } from "expo-router";
import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { Button } from "@/components/ui";
import { ApiError, bindElderDevice } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import { colors, elder, spacing } from "@/lib/theme";

const BIND_ERRORS: Record<string, string> = {
  invite_not_found: "找不到這組號碼，請跟家人再確認一次。",
  invite_used: "這組號碼已經用過了，請家人重新產生一組。",
  invite_expired: "這組號碼過期了，請家人重新產生一組。",
  too_many_attempts: "試太多次了，請家人重新產生一組。",
};

/** 長輩綁定：輸入家人給的綁定碼，一次就好，之後永久登入。 */
export default function ElderBind() {
  const router = useRouter();
  const { signIn } = useSession();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    setBusy(true);
    try {
      const session = await bindElderDevice(code.trim());
      await signIn({ role: "elder", token: session.token, display_name: session.name });
      router.replace("/elder/talk");
    } catch (exc) {
      if (exc instanceof ApiError && BIND_ERRORS[exc.code]) {
        setError(BIND_ERRORS[exc.code]);
      } else {
        setError("連不上金孫，請稍後再試一次。");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>請輸入家人給您的號碼</Text>
      <TextInput
        style={styles.codeInput}
        value={code}
        onChangeText={setCode}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder="綁定碼"
        placeholderTextColor={colors.textSoft}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Button label="開始使用" size="big" onPress={submit} busy={busy} disabled={!code.trim()} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    padding: spacing.xl,
    gap: spacing.l,
    justifyContent: "center",
  },
  hint: { fontSize: elder.fontMin, color: colors.text, textAlign: "center" },
  codeInput: {
    backgroundColor: colors.surface,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: 16,
    padding: spacing.l,
    fontSize: elder.fontBig,
    textAlign: "center",
    color: colors.text,
    letterSpacing: 2,
  },
  error: { fontSize: elder.fontMin, color: colors.danger, textAlign: "center" },
});
