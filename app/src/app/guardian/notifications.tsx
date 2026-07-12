import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";

import { EmptyHint, ErrorText } from "@/components/ui";
import { type AppNotification, listNotifications } from "@/lib/api";
import { saveSeenAt } from "@/lib/notificationsSeen";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { colors, spacing } from "@/lib/theme";
import { formatTime } from "kinsun-shared/format";

/** 家屬通知列表（✅ D-12）：警報／提醒／關懷訊息，最近先；開啟即更新已讀水位。 */
export default function GuardianNotifications() {
  const router = useRouter();
  const { loading: sessionLoading, session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  useFocusEffect(
    useCallback(() => {
      if (sessionLoading) {
        return;
      }
      if (!session || session.role !== "guardian") {
        router.replace("/role");
        return;
      }
      let alive = true;
      (async () => {
        try {
          const list = await listNotifications(session.token);
          if (alive) {
            setItems(list);
            setLoaded(true);
          }
          if (list.length > 0) {
            await saveSeenAt(list[0].created_at);
          }
        } catch (exc) {
          if (await signOutOn401(exc)) return;
          if (alive) {
            setError(exc instanceof Error ? exc.message : "載入失敗");
            setLoaded(true);
          }
        }
      })();
      return () => {
        alive = false;
      };
    }, [router, sessionLoading, session]),
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={items}
        keyExtractor={(n) => `${n.created_at}-${n.content}`}
        contentContainerStyle={styles.list}
        ListHeaderComponent={<ErrorText message={error} />}
        ListEmptyComponent={
          loaded ? <EmptyHint text="目前沒有通知。金孫有事會第一時間放在這裡。" /> : null
        }
        renderItem={({ item }) => (
          <View style={styles.row}>
            <Text style={styles.time}>{formatTime(item.created_at)}</Text>
            <Text style={styles.content}>{item.content}</Text>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.m, gap: spacing.s },
  row: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.l,
    gap: spacing.xs,
  },
  time: { fontSize: 13, color: colors.textSoft },
  content: { fontSize: 17, color: colors.text, lineHeight: 24 },
});
