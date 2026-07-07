import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Alert, FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import { createElder, listElders, type Elder } from "@/lib/api";
import { clearSession, loadSession } from "@/lib/auth";
import { colors, spacing } from "@/lib/theme";

/** 家屬首頁：長輩列表＋新增長輩（成功即顯示長輩綁定碼）。 */
export default function GuardianHome() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [elders, setElders] = useState<Elder[]>([]);
  const [newName, setNewName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useFocusEffect(
    useCallback(() => {
      let alive = true;
      loadSession().then(async (session) => {
        if (!session || session.role !== "guardian") {
          router.replace("/role");
          return;
        }
        setToken(session.token);
        try {
          const list = await listElders(session.token);
          if (alive) {
            setElders(list);
          }
        } catch (exc) {
          if (alive) {
            setError(exc instanceof Error ? exc.message : "載入失敗");
          }
        }
      });
      return () => {
        alive = false;
      };
    }, [router]),
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
          await clearSession();
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
          <Section title="新增長輩">
            <Field
              label="長輩稱呼"
              value={newName}
              onChangeText={setNewName}
              placeholder="例如：阿公"
            />
            <Button label="建立長輩檔案" onPress={addElder} busy={busy} />
            {inviteCode ? (
              <View style={styles.invite}>
                <Text style={styles.inviteHint}>長輩綁定碼（在長輩手機輸入一次即可）：</Text>
                <Text style={styles.inviteCode}>{inviteCode}</Text>
              </View>
            ) : null}
            <ErrorText message={error} />
          </Section>
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
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.m, gap: spacing.m },
  invite: {
    backgroundColor: colors.background,
    borderRadius: 12,
    padding: spacing.m,
    gap: spacing.xs,
  },
  inviteHint: { fontSize: 14, color: colors.textSoft },
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
  footer: { marginTop: spacing.l },
});
