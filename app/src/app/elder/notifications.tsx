import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { EmptyHint, ErrorText } from "@/components/ui";
import { type AppNotification, listElderNotifications } from "@/lib/api";
import { saveSeenAt } from "@/lib/notificationsSeen";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, elder, spacing } from "@/lib/theme";
import { formatTime } from "kinsun-shared/format";

/** 長輩的提醒列表（X-01，2026-07-29）：用藥／回診提醒與主動關懷，最近先。
 *
 * 與家屬版（`guardian/notifications.tsx`）刻意不共用元件：長輩版字級更大、
 * 行距更寬、返回鍵是 56dp 的大按鈕——共用會讓兩邊的排版約束互相拉扯。
 */
export default function ElderNotifications() {
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
      if (!session || session.role !== "elder") {
        router.replace("/role");
        return;
      }
      let alive = true;
      (async () => {
        try {
          const list = await listElderNotifications(session.token);
          if (alive) {
            setItems(list);
            setLoaded(true);
          }
          // 開啟即更新已讀水位：長輩不會去按「標示已讀」，看到就算看過。
          if (list.length > 0) {
            await saveSeenAt(list[0].created_at, "elder");
          }
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
    }, [router, sessionLoading, session, signOutOn401]),
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={items}
        keyExtractor={(n) => `${n.created_at}-${n.content}`}
        contentContainerStyle={styles.list}
        ListHeaderComponent={<ErrorText message={error} size="big" />}
        ListEmptyComponent={
          loaded ? <EmptyHint text={strings.elderNotifications.empty} size="big" /> : null
        }
        renderItem={({ item }) => (
          <View style={styles.row}>
            <Text style={styles.time}>
              {formatTime(item.created_at)}
            </Text>
            <Text style={styles.content}>
              {item.content}
            </Text>
          </View>
        )}
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={strings.elderNotifications.back}
        onPress={() => router.back()}
        style={styles.backButton}
      >
        <Text style={styles.backText}>
          {strings.elderNotifications.back}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.l, gap: spacing.m },
  row: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.l,
    gap: spacing.xs,
  },
  time: { fontSize: elder.fontMin, color: colors.textSoft },
  content: { fontSize: elder.fontMin, color: colors.text, lineHeight: 34 },
  backButton: {
    margin: spacing.l,
    minHeight: 56,
    borderRadius: 28,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  backText: { fontSize: elder.fontMin, color: colors.text },
});
