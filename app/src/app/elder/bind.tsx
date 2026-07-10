import { CameraView, useCameraPermissions } from "expo-camera";
import { useRouter } from "expo-router";
import { useRef, useState } from "react";
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

/** 長輩綁定：掃家人給的 QR（✅ D-54 丁-3）或輸入綁定碼，一次就好，之後永久登入。 */
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
        setError("連不上金孫，請稍後再試一次。");
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
        setError("需要相機權限才能掃描，也可以直接輸入號碼。");
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
        <Text style={styles.hint}>把家人給的方塊圖對準框框</Text>
        <CameraView
          style={styles.camera}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
          onBarcodeScanned={({ data }) => onScanned(data)}
        />
        <Button label="改用輸入號碼" variant="outline" onPress={() => setScanning(false)} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>掃描家人給的方塊圖，或輸入號碼</Text>
      <Button label="掃描 QR 碼" size="big" onPress={startScan} disabled={busy} />
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
      <Button
        label="開始使用"
        size="big"
        onPress={() => submit(code)}
        busy={busy}
        disabled={!code.trim()}
      />
      {/* 帳密只管「重登」（✅ D-71 己-6）：換手機或登出後走這裡，首次仍要掃碼配對。 */}
      <Button
        label="用過金孫？帳號密碼登入"
        variant="outline"
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
