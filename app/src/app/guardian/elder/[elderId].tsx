import { useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Section } from "@/components/ui";
import {
  createGuardianInvite,
  getHealthReport,
  listAppointments,
  listMedications,
  type Appointment,
  type HealthReport,
  type Medication,
} from "@/lib/api";
import { loadSession } from "@/lib/auth";
import { colors, spacing } from "@/lib/theme";

const SLOT_LABELS: Record<string, string> = {
  morning: "早上",
  noon: "中午",
  evening: "晚上",
  bedtime: "睡前",
};

const TIER_LABELS: Record<number, string> = { 2: "需留意", 3: "危急" };

function formatTime(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;
}

/** 長輩詳情：用藥／回診／健康報告／家屬邀請碼，單頁分區塊。 */
export default function ElderDetail() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const [medications, setMedications] = useState<Medication[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [report, setReport] = useState<HealthReport | null>(null);
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");

  useEffect(() => {
    let alive = true;
    loadSession().then(async (session) => {
      if (!session || !elderId) {
        return;
      }
      setToken(session.token);
      try {
        const [meds, appts, hr] = await Promise.all([
          listMedications(elderId, session.token),
          listAppointments(elderId, session.token),
          getHealthReport(elderId, session.token),
        ]);
        if (alive) {
          setMedications(meds);
          setAppointments(appts);
          setReport(hr);
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
  }, [elderId]);

  async function makeInvite() {
    if (!elderId) {
      return;
    }
    setBusy(true);
    try {
      setInviteCode(await createGuardianInvite(elderId, token));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "產生邀請碼失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <ErrorText message={error} />

      <Section title="健康報告（近 30 天）">
        {report === null ? (
          <EmptyHint text="載入中…" />
        ) : (
          <View style={styles.reportBody}>
            {report.risk_events.length === 0 ? (
              <Text style={styles.ok}>沒有危急事件，一切平安。</Text>
            ) : (
              report.risk_events.map((e, i) => (
                <Text key={`risk-${i}`} style={styles.risk}>
                  {formatTime(e.created_at)}｜{TIER_LABELS[e.tier] ?? `L${e.tier}`}｜{e.reason}
                </Text>
              ))
            )}
            {report.reminders.length > 0 ? (
              <Text style={styles.soft}>近 30 天提醒 {report.reminders.length} 則</Text>
            ) : null}
          </View>
        )}
      </Section>

      <Section title="固定用藥">
        {medications.length === 0 ? (
          <EmptyHint text="尚未設定用藥（可先在 LINE 端設定，App 版編輯後續提供）。" />
        ) : (
          medications.map((m) => (
            <Text key={m.medication_id} style={styles.row}>
              {m.name}（{m.slots.map((s) => SLOT_LABELS[s] ?? s).join("、")}）
            </Text>
          ))
        )}
      </Section>

      <Section title="即將回診">
        {appointments.length === 0 ? (
          <EmptyHint text="沒有排定的回診。" />
        ) : (
          appointments.map((a) => (
            <Text key={a.appointment_id} style={styles.row}>
              {a.date}｜{a.label}
            </Text>
          ))
        )}
      </Section>

      <Section title="邀請其他家屬">
        <Button label="產生家屬邀請碼" onPress={makeInvite} busy={busy} variant="outline" />
        {inviteCode ? <Text style={styles.inviteCode}>{inviteCode}</Text> : null}
      </Section>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.m, gap: spacing.m },
  reportBody: { gap: spacing.xs },
  ok: { fontSize: 16, color: colors.success },
  risk: { fontSize: 16, color: colors.danger },
  soft: { fontSize: 14, color: colors.textSoft },
  row: { fontSize: 17, color: colors.text },
  inviteCode: { fontSize: 26, fontWeight: "800", color: colors.primary, letterSpacing: 1 },
});
