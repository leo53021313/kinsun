/**
 * 危急詳情安全降級骨架（批次 6）。
 *
 * 後續完整功能必須同時具備：通知與風險事件 ID、三支詳情／處理端點、同意版本、
 * 每次查閱稽核，以及 30 天後刪除錄音與逐字的排程。缺一不可；本版不呼叫不存在的
 * API，也不從通知清單連入，避免把敏感內容或無效按鈕誤當成已上線功能。
 */

import { WarningCircleIcon } from "phosphor-react-native/src/icons/WarningCircle";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Section, StatusPill } from "@/components/ui";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

export default function CriticalAlertDetailScreen() {
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <StatusPill
        tone="critical"
        label={strings.criticalAlert.safeFallbackTitle}
        icon={<WarningCircleIcon size={20} weight="bold" color={colors.dangerText} />}
      />

      <Section>
        <View style={styles.fact}>
          <Text style={styles.label}>{strings.criticalAlert.reasonLabel}</Text>
          <Text style={styles.value}>{strings.criticalAlert.reasonUnavailable}</Text>
        </View>
        <View style={styles.fact}>
          <Text style={styles.label}>{strings.criticalAlert.timeLabel}</Text>
          <Text style={styles.value}>{strings.criticalAlert.timeUnavailable}</Text>
        </View>
      </Section>

      <Text style={styles.note}>{strings.criticalAlert.safeFallbackBody}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.m, gap: spacing.m },
  fact: { gap: spacing.xs },
  label: { fontSize: 15, fontWeight: "700", color: colors.textSoft },
  value: { fontSize: 18, lineHeight: 27, color: colors.text },
  note: { fontSize: 16, lineHeight: 25, color: colors.textSoft },
});
