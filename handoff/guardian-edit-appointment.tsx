/** 改回診時間（批次 6）。updateSchedule API 已存在。
 *
 * 三個決定：新時間、誰帶去、要不要讓阿白告訴長輩。
 * 刻意提醒「阿白不會幫您打電話改掛號」——避免家屬以為系統代辦到底。
 */

import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, Chip, ErrorText, Field, Section } from "@/components/ui";
import { deleteSchedule, updateSchedule } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import { colors, radius, spacing } from "@/lib/theme";
import { strings } from "@/lib/strings";

const DRIVERS = ["我去", "其他家人", "他自己去"] as const;

export default function EditAppointment() {
  const router = useRouter();
  const { scheduleId, elderId } = useLocalSearchParams<{ scheduleId: string; elderId: string }>();
  const { session } = useSession();
  const [when, setWhen] = useState("");
  const [driver, setDriver] = useState<string>(DRIVERS[0]);
  const [tellElder, setTellElder] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!session || !scheduleId) return;
    if (!when.trim()) {
      setError(strings.schedules.whenRequired);
      return;
    }
    setBusy(true);
    try {
      await updateSchedule(scheduleId, { when, driver, notify_elder: tellElder }, session.token);
      router.back();
    } catch {
      setError(strings.common.saveFailed);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!session || !scheduleId) return;
    try {
      await deleteSchedule(scheduleId, session.token);
      router.back();
    } catch {
      setError(strings.common.deleteFailed);
    }
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Field
        label={strings.editAppointment.whenLabel}
        value={when}
        onChangeText={setWhen}
        placeholder={strings.schedules.whenPlaceholder("appointment")}
        hint={strings.editAppointment.whenHint}
      />

      <View style={styles.group}>
        <Text style={styles.label} maxFontSizeMultiplier={1.6}>
          {strings.editAppointment.driverLabel}
        </Text>
        <View style={styles.chipRow}>
          {DRIVERS.map((d) => (
            <Chip key={d} label={d} role="radio" selected={driver === d} onPress={() => setDriver(d)} />
          ))}
        </View>
      </View>

      <Section>
        <View style={styles.toggleRow}>
          <View style={styles.toggleText}>
            <Text style={styles.toggleTitle} maxFontSizeMultiplier={1.6}>
              {strings.editAppointment.tellElderLabel}
            </Text>
            <Text style={styles.toggleHelp} maxFontSizeMultiplier={2}>
              {strings.editAppointment.tellElderHelp}
            </Text>
          </View>
          <Button
            label={tellElder ? strings.common.on : strings.common.off}
            variant={tellElder ? "primary" : "subtle"}
            onPress={() => setTellElder((v) => !v)}
          />
        </View>
      </Section>

      {/* 長輩那端只會聽到新時間，不會看到「誰改的、改過幾次」 */}
      <Text style={styles.note} maxFontSizeMultiplier={2}>
        {strings.editAppointment.elderSeesOnlyNewTime}
      </Text>

      <ErrorText message={error} />
      <Button label={strings.editAppointment.save} onPress={save} busy={busy} />

      {/* 破壞性動作放最後，用外框紅並引用行程名稱 */}
      <Button
        label={strings.editAppointment.deleteThis}
        variant="danger"
        onPress={remove}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.m, gap: spacing.l },
  group: { gap: spacing.s },
  label: { fontSize: 16, fontWeight: "600", color: colors.text },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.s + 2 },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.m },
  toggleText: { flex: 1, gap: spacing.xs },
  toggleTitle: { fontSize: 18, fontWeight: "700", color: colors.text },
  toggleHelp: { fontSize: 16, lineHeight: 24, color: colors.textSoft },
  note: { fontSize: 16, lineHeight: 25, color: colors.textSoft },
});
