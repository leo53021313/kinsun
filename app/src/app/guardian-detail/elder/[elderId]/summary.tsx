/** 每日摘要（批次 6）：後端目前只提供日期、純文字摘要與建立時間。 */

import { useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { CaretLeftIcon } from "phosphor-react-native/src/icons/CaretLeft";
import { CaretRightIcon } from "phosphor-react-native/src/icons/CaretRight";
import { Pressable, ScrollView, Share, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Section } from "@/components/ui";
import { listDailySummaries } from "@/lib/api";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, radius, spacing } from "@/lib/theme";
import type { DailySummary } from "kinsun-shared/types";

export default function DailySummaryScreen() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const { session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const [items, setItems] = useState<DailySummary[]>([]);
  // API 由新到舊排序；index 0 是最新一天，往左看才是前一天。
  const [index, setIndex] = useState(0);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    if (!session || !elderId) return;
    let alive = true;
    (async () => {
      try {
        const list = await listDailySummaries(elderId, session.token);
        if (alive) {
          setItems(list);
          setIndex(0);
        }
      } catch (exc) {
        if (await signOutOn401(exc)) return;
        if (alive) setError(strings.common.loadFailed);
      } finally {
        if (alive) setLoaded(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [elderId, loadAttempt, session, signOutOn401]);

  const current = items[index];

  function retry() {
    setError("");
    setLoaded(false);
    setLoadAttempt((value) => value + 1);
  }

  async function shareCurrent() {
    if (!current) return;
    try {
      await Share.share({ message: buildShareText(current) });
    } catch {
      setError(strings.dailySummary.shareFailed);
    }
  }

  if (!loaded) {
    return (
      <View style={styles.stateScreen}>
        <EmptyHint text={strings.common.loading} />
      </View>
    );
  }

  if (error && items.length === 0) {
    return (
      <View style={styles.stateScreen}>
        <ErrorText message={error} />
        <Button label={strings.common.retry} variant="outline" onPress={retry} />
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View style={styles.stateScreen}>
        <EmptyHint text={strings.elderDetail.noSummaries} />
      </View>
    );
  }

  const isOldest = index >= items.length - 1;
  const isNewest = index === 0;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.dateBar}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={strings.dailySummary.prevDay}
          accessibilityState={{ disabled: isOldest }}
          disabled={isOldest}
          onPress={() => setIndex((value) => Math.min(value + 1, items.length - 1))}
          style={[styles.dateArrow, isOldest ? styles.dateArrowDisabled : null]}
        >
          <CaretLeftIcon
            size={22}
            weight="bold"
            color={isOldest ? colors.textSoft : colors.primary}
          />
        </Pressable>
        <Text style={styles.dateLabel} maxFontSizeMultiplier={2}>
          {current.date}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={strings.dailySummary.nextDay}
          accessibilityState={{ disabled: isNewest }}
          disabled={isNewest}
          onPress={() => setIndex((value) => Math.max(value - 1, 0))}
          style={[styles.dateArrow, isNewest ? styles.dateArrowDisabled : null]}
        >
          <CaretRightIcon
            size={22}
            weight="bold"
            color={isNewest ? colors.textSoft : colors.primary}
          />
        </Pressable>
      </View>

      <ErrorText message={error} />

      <Section title={strings.dailySummary.section}>
        <Text style={styles.body} maxFontSizeMultiplier={2}>
          {current.content}
        </Text>
      </Section>

      <Text style={styles.note} maxFontSizeMultiplier={2}>
        {strings.dailySummary.disclaimer}
      </Text>

      <Button label={strings.dailySummary.share} onPress={shareCurrent} />
    </ScrollView>
  );
}

export function buildShareText(summary: DailySummary): string {
  return `${summary.date} 的摘要\n\n${summary.content}\n\n（由金孫產生）`;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  stateScreen: {
    flex: 1,
    backgroundColor: colors.background,
    padding: spacing.m,
    gap: spacing.m,
  },
  content: { padding: spacing.m, gap: spacing.m },
  dateBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    padding: spacing.xs,
  },
  dateArrow: { width: 48, height: 48, alignItems: "center", justifyContent: "center" },
  dateArrowDisabled: { opacity: 0.45 },
  dateLabel: { fontSize: 17, fontWeight: "700", color: colors.text },
  body: { fontSize: 18, lineHeight: 29, color: colors.text },
  note: { fontSize: 16, lineHeight: 25, color: colors.textSoft },
});
