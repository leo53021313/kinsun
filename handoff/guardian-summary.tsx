/** 每日摘要（批次 6）。listDailySummaries API 已存在。
 *
 * ⚠ 型別核對結果（shared/types.ts:43）：
 *   DailySummary = { date: string; content: string; created_at: number }
 *   後端只回一段純文字，沒有結構化欄位。
 *
 * 因此設計稿的三層結構（原話／觀察／四個數字）**這一版做不出來**。
 * 這裡照真實型別做：一段摘要文字＋日期切換＋分享。
 * 要做三層版本得先讓後端把摘要拆成結構化欄位——見批次 6 說明的「後端待辦」。
 */

import { useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { CaretLeftIcon } from "phosphor-react-native/src/icons/CaretLeft";
import { CaretRightIcon } from "phosphor-react-native/src/icons/CaretRight";
import { Pressable, ScrollView, Share, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, Section } from "@/components/ui";
import { listDailySummaries } from "@/lib/api";
import type { DailySummary } from "kinsun-shared/types";
import { useSession } from "@/lib/SessionProvider";
import { colors, radius, spacing } from "@/lib/theme";
import { strings } from "@/lib/strings";

export default function DailySummaryScreen() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const { session } = useSession();
  const [items, setItems] = useState<DailySummary[]>([]);
  // 0 = 最新那天；往後翻是往回看，所以 index 越大日期越舊（API 回的是新到舊）
  const [index, setIndex] = useState(0);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!session || !elderId) return;
    let alive = true;
    (async () => {
      try {
        const list = await listDailySummaries(elderId, session.token);
        if (alive) {
          setItems(list);
          setLoaded(true);
        }
      } catch {
        if (alive) {
          setError(strings.common.loadFailed);
          setLoaded(true);
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [session, elderId]);

  const current = items[index];

  if (loaded && items.length === 0) {
    return (
      <View style={styles.emptyScreen}>
        <EmptyHint text={strings.elderDetail.noSummaries} />
      </View>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {/* 日期切換。最新那天不能再往新的翻。 */}
      <View style={styles.dateBar}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={strings.dailySummary.prevDay}
          disabled={index >= items.length - 1}
          onPress={() => setIndex((i) => Math.min(i + 1, items.length - 1))}
          style={[styles.dateArrow, index >= items.length - 1 ? styles.dateArrowDisabled : null]}
        >
          <CaretLeftIcon size={20} weight="bold" color={colors.primary} />
        </Pressable>
        <Text style={styles.dateLabel} maxFontSizeMultiplier={1.6}>
          {current?.date ?? ""}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={strings.dailySummary.nextDay}
          disabled={index === 0}
          onPress={() => setIndex((i) => Math.max(i - 1, 0))}
          style={[styles.dateArrow, index === 0 ? styles.dateArrowDisabled : null]}
        >
          <CaretRightIcon size={20} weight="bold" color={colors.textSoft} />
        </Pressable>
      </View>

      {error ? <EmptyHint text={error} /> : null}

      <Section title={strings.dailySummary.section}>
        <Text style={styles.body} maxFontSizeMultiplier={2}>
          {current?.content ?? ""}
        </Text>
      </Section>

      {/* 摘要是阿白整理的，不是長輩的原話——這一行不可以拿掉，
          否則家屬會把它當逐字紀錄看待。 */}
      <Text style={styles.note} maxFontSizeMultiplier={2}>
        {strings.dailySummary.disclaimer}
      </Text>

      <Button
        label={strings.dailySummary.share}
        onPress={() => Share.share({ message: buildShareText(current) })}
      />
    </ScrollView>
  );
}

function buildShareText(s?: DailySummary): string {
  if (!s) return "";
  return `${s.date} 的摘要\n\n${s.content}\n\n（由金孫產生）`;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  emptyScreen: { flex: 1, backgroundColor: colors.background, padding: spacing.m },
  content: { padding: spacing.m, gap: spacing.m },
  dateBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    padding: 6,
  },
  dateArrow: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  dateArrowDisabled: { opacity: 0.4 },
  dateLabel: { fontSize: 17, fontWeight: "700", color: colors.text },
  body: { fontSize: 18, lineHeight: 29, color: colors.text },
  note: { fontSize: 16, lineHeight: 25, color: colors.textSoft },
});
