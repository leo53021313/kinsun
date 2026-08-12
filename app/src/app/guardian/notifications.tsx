import { useFocusEffect, useNavigation, usePathname, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";

import { EmptyHint, ErrorText } from "@/components/ui";
import { type AppNotification, listNotifications } from "@/lib/api";
import { loadSeenAt, saveSeenAt } from "@/lib/notificationsSeen";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";
import { formatTime } from "kinsun-shared/format";

/** 家屬通知列表（✅ D-12）：警報／提醒／關懷訊息，最近先；開啟即更新已讀水位。 */
export default function GuardianNotifications() {
  const router = useRouter();
  const navigation = useNavigation();
  const pathname = usePathname();
  const { loading: sessionLoading, session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  // Tabs 以 lazy:false 預載本頁；即使使用者還在首頁，也由本頁自己設定未讀徽章。
  // layout 不讀 session，避免把通知資料責任拉進導航層。
  useEffect(() => {
    if (sessionLoading || !session || session.role !== "guardian") return;
    if (pathname === "/guardian/notifications") return;

    let alive = true;
    void Promise.all([listNotifications(session.token), loadSeenAt()])
      .then(([list, seenAt]) => {
        if (!alive) return;
        const unreadCount = list.filter((item) => item.created_at > seenAt).length;
        navigation.setOptions({ tabBarBadge: unreadCount > 0 ? unreadCount : undefined });
      })
      .catch(() => {
        // 徽章是加分資訊；失敗不影響其他 tab，也不覆蓋目前畫面錯誤狀態。
      });
    return () => {
      alive = false;
    };
  }, [navigation, pathname, session, sessionLoading]);

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
            setError("");
            setLoaded(true);
          }
          if (list.length > 0) {
            await saveSeenAt(Math.max(...list.map((item) => item.created_at)));
          }
          if (alive) navigation.setOptions({ tabBarBadge: undefined });
        } catch (exc) {
          if (await signOutOn401(exc)) return;
          if (alive) {
            setError(exc instanceof Error ? exc.message : strings.common.loadFailedShort);
            setLoaded(true);
          }
        }
      })();
      return () => {
        alive = false;
      };
    }, [navigation, router, sessionLoading, session, signOutOn401]),
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={items}
        keyExtractor={(n) => `${n.created_at}-${n.content}`}
        contentContainerStyle={styles.list}
        ListHeaderComponent={<ErrorText message={error} />}
        ListEmptyComponent={
          loaded ? <EmptyHint text={strings.notifications.empty} /> : null
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
