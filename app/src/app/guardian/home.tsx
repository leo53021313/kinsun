import * as Clipboard from "expo-clipboard";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Alert, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import QRCode from "react-native-qrcode-svg";

import { RoleSwitcher } from "@/components/RoleSwitcher";
import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import { createElder, listElders, listNotifications, logoutGuardian, type Elder } from "@/lib/api";
import { loadSeenAt } from "@/lib/notificationsSeen";
import { useGuardianTabsState } from "@/lib/GuardianTabsProvider";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
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
  const { refreshPrimaryElder } = useGuardianTabsState();

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
            setError(exc instanceof Error ? exc.message : strings.common.loadFailedShort);
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
    }, [router, loading, session, signOutOn401]),
  );

  async function addElder() {
    const name = newName.trim();
    if (!name) {
      setError(strings.guardianHome.nameRequired);
      return;
    }
    setError("");
    setBusy(true);
    try {
      // 拆掉 invite_code、其餘原樣進列表：`CreatedElder = Elder & { invite_code }`，
      // 所以剩下的部分**就是** Elder，不必逐欄位抄。
      //
      // ⚠️ 原本是逐欄位列舉，而這裡已經漏過兩次：先漏 nickname（A-10，2026-07-29，
      // 剛新增的那筆在列表上少一個稱謂、要重新整理才會出現），再漏 persona（人設功能
      // 加欄位時沒回頭改這裡）。逐欄位抄的寫法保證會有第三次——`Elder` 每加一個欄位
      // 就要記得回來補，而忘記的代價是「新增後畫面資料不全」這種要重整才會發現的症狀。
      const { invite_code: inviteCode, ...created } = await createElder(name, token);
      setElders((prev) => [...prev, created]);
      setInviteCode(inviteCode);
      setNewName("");
      void refreshPrimaryElder();
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setError(exc instanceof Error ? exc.message : strings.guardianHome.addFailed);
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    Alert.alert(strings.guardianHome.logout, strings.guardianHome.logoutConfirm, [
      { text: strings.common.cancel, style: "cancel" },
      {
        text: strings.guardianHome.logout,
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
              <Text style={styles.notifyLabel}>{strings.guardianHome.notify}</Text>
              <View style={styles.notifyRight}>
                {unreadCount > 0 ? (
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>{unreadCount}</Text>
                  </View>
                ) : null}
                <Text style={styles.elderArrow}>›</Text>
              </View>
            </Pressable>
            <Section title={strings.guardianHome.addElderSection}>
              <Field
                label={strings.guardianHome.elderNameLabel}
                value={newName}
                onChangeText={setNewName}
                placeholder={strings.guardianHome.elderNamePlaceholder}
              />
              {/* 代辦同意文案（✅ 己-2）：資料去向＋永久保留＋團隊可讀，按建立即代為同意。 */}
              <Text style={styles.consentText}>{strings.guardianHome.consent}</Text>
              {/* ⚠️ variant=outline 而非預設的 primary：規則 14「暖黃是每頁唯一主要
                  行動」。分頁畫面的底部常駐著中央凸出的暖黃鍵（新增提醒），頁內再放
                  一顆暖黃就是一屏兩個主要行動——而且是每一個分頁都違反。暖黃留給
                  導覽列那顆，頁內動作用靛藍外框。 */}
              <Button
                label={strings.guardianHome.createElder}
                variant="outline"
                onPress={addElder}
                busy={busy}
              />
              {/* 綁定碼面板＝「凹一階」的內嵌區塊，正是 Section 的 inset 在做的事。
                  原本手寫 styles.invite，圓角 12 是全庫唯一沒對上 radius token 的
                  內嵌區塊（inset 是 radius.control＝16）。 */}
              {inviteCode ? (
                <Section inset>
                  <Text style={styles.inviteHint}>{strings.guardianHome.inviteHint}</Text>
                  <Text style={styles.inviteCode} selectable>
                    {inviteCode}
                  </Text>
                  {/* QR 掃碼綁定（✅ D-54 丁-3）：長輩端「掃描家人給的 QR」免打字。 */}
                  <View style={styles.qrBox}>
                    <QRCode value={inviteCode} size={168} />
                  </View>
                  <Button
                    label={strings.guardianHome.copyCode}
                    variant="outline"
                    onPress={async () => {
                      await Clipboard.setStringAsync(inviteCode);
                      Alert.alert(strings.guardianHome.copiedTitle, strings.guardianHome.copiedMessage);
                    }}
                  />
                </Section>
              ) : null}
              <ErrorText message={error} />
            </Section>
          </View>
        }
        ListEmptyComponent={<EmptyHint text={strings.guardianHome.empty} />}
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              router.push({
                pathname: "/guardian-detail/elder/[elderId]",
                params: { elderId: item.elder_id },
              })
            }
            style={({ pressed }) => [styles.elderRow, pressed ? styles.elderRowPressed : null]}
          >
            <Text style={styles.elderName}>{item.name}</Text>
            <Text style={styles.elderArrow}>›</Text>
          </Pressable>
        )}
        ListFooterComponent={
          <View style={styles.footer}>
            <Button label={strings.guardianHome.logout} variant="outline" onPress={logout} />
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
