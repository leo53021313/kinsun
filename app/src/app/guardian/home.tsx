import * as Clipboard from "expo-clipboard";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Alert, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import QRCode from "react-native-qrcode-svg";

import { RoleSwitcher } from "@/components/RoleSwitcher";
import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import { createElder, listElders, listNotifications, logoutGuardian, type Elder } from "@/lib/api";
import { loadSeenAt } from "@/lib/notificationsSeen";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { colors, spacing } from "@/lib/theme";

/** 家屬首頁：長輩列表＋新增長輩（成功即顯示長輩綁定碼）。 */
export default function GuardianHome() {
  const router = useRouter();
  const { loading, session, signOut } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const token = session?.token ?? "";
  const [elders, setElders] = useState<Elder[]>([]);
  const [newName, setNewName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  useFocusEffect(
    useCallback(() => {
      if (loading) {
        return;
      }
      if (!session || session.role !== "guardian") {
        router.replace("/role");
        return;
      }
      let alive = true;
      (async () => {
        try {
          const list = await listElders(session.token);
          if (alive) {
            setElders(list);
          }
        } catch (exc) {
          if (await signOutOn401(exc)) return;
          if (alive) {
            setError(exc instanceof Error ? exc.message : "載入失敗");
          }
        }
        try {
          // 未讀 badge（✅ D-12）：比「已讀水位」新的通知數；失敗不影響主畫面。
          const [notifications, seenAt] = await Promise.all([
            listNotifications(session.token),
            loadSeenAt(),
          ]);
          if (alive) {
            setUnreadCount(notifications.filter((n) => n.created_at > seenAt).length);
          }
        } catch {
          // 通知載入失敗時 badge 保持 0，主功能不受影響。
        }
      })();
      return () => {
        alive = false;
      };
    }, [router, loading, session]),
  );

  async function addElder() {
    const name = newName.trim();
    if (!name) {
      setError("請先輸入長輩的稱呼。");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const created = await createElder(name, token);
      setElders((prev) => [...prev, { elder_id: created.elder_id, name: created.name }]);
      setInviteCode(created.invite_code);
      setNewName("");
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setError(exc instanceof Error ? exc.message : "新增失敗");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    Alert.alert("登出", "確定要登出嗎？", [
      { text: "取消", style: "cancel" },
      {
        text: "登出",
        style: "destructive",
        onPress: async () => {
          // 先撤銷伺服器端 token（✅ D-25 修訂）；離線也不擋本機登出。
          await logoutGuardian(token).catch(() => undefined);
          await signOut();
          router.replace("/role");
        },
      },
    ]);
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={elders}
        keyExtractor={(e) => e.elder_id}
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <View style={styles.header}>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.push("/guardian/notifications")}
              style={({ pressed }) => [
                styles.notifyRow,
                pressed ? styles.elderRowPressed : null,
              ]}
            >
              <Text style={styles.notifyLabel}>通知</Text>
              <View style={styles.notifyRight}>
                {unreadCount > 0 ? (
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>{unreadCount}</Text>
                  </View>
                ) : null}
                <Text style={styles.elderArrow}>›</Text>
              </View>
            </Pressable>
            <Section title="新增長輩">
              <Field
                label="長輩稱呼"
                value={newName}
                onChangeText={setNewName}
                placeholder="例如：阿公"
              />
              {/* 代辦同意文案（✅ 己-2）：資料去向＋永久保留＋團隊可讀，按建立即代為同意。 */}
              <Text style={styles.consentText}>
                建立後，金孫會記錄長輩與它的對話內容（文字與語音），用來陪伴關懷、產生每日摘要、
                偵測到危急狀況時通知家人；資料會一直保留，開發團隊為了改善服務可檢視內容。
                按下「建立長輩檔案」即代表您替長輩同意以上事項。
              </Text>
              <Button label="建立長輩檔案" onPress={addElder} busy={busy} />
              {inviteCode ? (
                <View style={styles.invite}>
                  <Text style={styles.inviteHint}>長輩綁定碼（在長輩手機輸入或掃描一次即可）：</Text>
                  <Text style={styles.inviteCode} selectable>
                    {inviteCode}
                  </Text>
                  {/* QR 掃碼綁定（✅ D-54 丁-3）：長輩端「掃描家人給的 QR」免打字。 */}
                  <View style={styles.qrBox}>
                    <QRCode value={inviteCode} size={168} />
                  </View>
                  <Button
                    label="複製綁定碼"
                    variant="outline"
                    onPress={async () => {
                      await Clipboard.setStringAsync(inviteCode);
                      Alert.alert("已複製", "綁定碼已複製，可貼給家人或長輩。");
                    }}
                  />
                </View>
              ) : null}
              <ErrorText message={error} />
            </Section>
          </View>
        }
        ListEmptyComponent={<EmptyHint text="還沒有長輩檔案，先在上面建立一位吧。" />}
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push(`/guardian/elder/${item.elder_id}`)}
            style={({ pressed }) => [styles.elderRow, pressed ? styles.elderRowPressed : null]}
          >
            <Text style={styles.elderName}>{item.name}</Text>
            <Text style={styles.elderArrow}>›</Text>
          </Pressable>
        )}
        ListFooterComponent={
          <View style={styles.footer}>
            <Button label="登出" variant="outline" onPress={logout} />
            <RoleSwitcher />
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.m, gap: spacing.m },
  header: { gap: spacing.m },
  notifyRow: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.l,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  notifyLabel: { fontSize: 20, fontWeight: "700", color: colors.text },
  notifyRight: { flexDirection: "row", alignItems: "center", gap: spacing.s },
  badge: {
    minWidth: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 6,
  },
  badgeText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  invite: {
    backgroundColor: colors.background,
    borderRadius: 12,
    padding: spacing.m,
    gap: spacing.s,
  },
  qrBox: { alignSelf: "center", backgroundColor: "#FFFFFF", padding: spacing.m, borderRadius: 12 },
  inviteHint: { fontSize: 14, color: colors.textSoft },
  consentText: { fontSize: 13, color: colors.textSoft, lineHeight: 19 },
  inviteCode: { fontSize: 26, fontWeight: "800", color: colors.primary, letterSpacing: 1 },
  elderRow: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.l,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  elderRowPressed: { backgroundColor: colors.border },
  elderName: { fontSize: 20, fontWeight: "700", color: colors.text },
  elderArrow: { fontSize: 26, color: colors.textSoft },
  footer: { marginTop: spacing.l, gap: spacing.m },
});
