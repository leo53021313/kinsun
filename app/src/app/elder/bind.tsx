import { CameraView, useCameraPermissions } from "expo-camera";
import { useRouter } from "expo-router";
import { useRef, useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { Button } from "@/components/ui";
import { ApiError, bindElderDevice } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, elder, spacing } from "@/lib/theme";

const BIND_ERRORS: Record<string, string> = {
  invite_not_found: strings.elderBind.inviteNotFound,
  invite_used: strings.elderBind.inviteUsed,
  invite_expired: strings.elderBind.inviteExpired,
  too_many_attempts: strings.elderBind.tooManyAttempts,
};

/** 長輩綁定：掃家人給的方塊圖（✅ D-54 丁-3）或輸入綁定碼，一次就好，之後永久登入。 */
export default function ElderBind() {
  const router = useRouter();
  const { signIn } = useSession();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();
  const scannedOnce = useRef(false);

  async function submit(rawCode: string) {
    setError("");
    setBusy(true);
    try {
      const session = await bindElderDevice(rawCode.trim());
      await signIn({ role: "elder", token: session.token, display_name: session.name });
      router.replace("/elder/talk");
    } catch (exc) {
      if (exc instanceof ApiError && BIND_ERRORS[exc.code]) {
        setError(BIND_ERRORS[exc.code]);
      } else {
        setError(strings.elderBind.bindFailed);
      }
    } finally {
      setBusy(false);
    }
  }

  async function startScan() {
    setError("");
    if (!permission?.granted) {
      const asked = await requestPermission();
      if (!asked.granted) {
        setError(strings.elderBind.cameraPermission);
        return;
      }
    }
    scannedOnce.current = false;
    setScanning(true);
  }

  function onScanned(data: string) {
    // CameraView 每個 frame 都可能重複回報：只取第一次。
    if (scannedOnce.current) {
      return;
    }
    scannedOnce.current = true;
    setScanning(false);
    setCode(data.trim());
    void submit(data);
  }

  if (scanning) {
    return (
      <View style={styles.container}>
        <Text style={styles.hint}>{strings.elderBind.scanHint}</Text>
        <CameraView
          style={styles.camera}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
          onBarcodeScanned={({ data }) => onScanned(data)}
        />
        <Button
          label={strings.elderBind.switchToManual}
          variant="outline"
          size="big"
          onPress={() => setScanning(false)}
        />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>{strings.elderBind.hint}</Text>
      <Button
        label={strings.elderBind.scanQr}
        variant="outline"
        size="big"
        onPress={startScan}
        disabled={busy}
      />
      <TextInput
        style={styles.codeInput}
        value={code}
        onChangeText={setCode}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder={strings.elderBind.codePlaceholder}
        placeholderTextColor={colors.textSoft}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Button
        label={strings.elderBind.start}
        size="big"
        onPress={() => submit(code)}
        busy={busy}
        disabled={!code.trim()}
      />
      {/* 帳密只管「重登」（✅ D-71 己-6）：換手機或登出後走這裡，首次仍要掃碼配對。 */}
      <Button
        label={strings.elderBind.loginLink}
        variant="outline"
        size="big"
        onPress={() => router.push("/elder/login")}
        disabled={busy}
      />
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
  camera: { flex: 1, borderRadius: 16, overflow: "hidden" },
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
