import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import {
  ApiError,
  createGuardianInvite,
  getHealthReport,
  listAppointments,
  listDailySummaries,
  listMedications,
  setElderAccount,
  type Appointment,
  type DailySummary,
  type HealthReport,
  type Medication,
} from "@/lib/api";
import { slotLabel } from "@/lib/medicationSlots";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { formatTime } from "kinsun-shared/format";
import { tierLabel } from "kinsun-shared/terms";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

/** 長輩詳情：用藥／回診／健康報告／家屬邀請碼，單頁分區塊。 */
export default function ElderDetail() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const [medications, setMedications] = useState<Medication[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [report, setReport] = useState<HealthReport | null>(null);
  const [summaries, setSummaries] = useState<DailySummary[] | null>(null);
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [accountPhone, setAccountPhone] = useState("");
  const [accountPassword, setAccountPassword] = useState("");
  const [accountMessage, setAccountMessage] = useState("");
  const [accountBusy, setAccountBusy] = useState(false);
  const { session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const token = session?.token ?? "";
  const router = useRouter();

  // useFocusEffect：從用藥／回診管理頁返回時重載，畫面才會反映剛做的編輯。
  useFocusEffect(
    useCallback(() => {
      if (!session || !elderId) {
        return;
      }
      let alive = true;
      (async () => {
        try {
          const [meds, appts, hr, daily] = await Promise.all([
            listMedications(elderId, session.token),
            listAppointments(elderId, session.token),
            getHealthReport(elderId, session.token),
            listDailySummaries(elderId, session.token),
          ]);
          if (alive) {
            setMedications(meds);
            setAppointments(appts);
            setReport(hr);
            setSummaries(daily);
          }
        } catch (exc) {
          if (await signOutOn401(exc)) return;
          if (alive) {
            setError(exc instanceof Error ? exc.message : strings.common.loadFailedShort);
          }
        }
      })();
      return () => {
        alive = false;
      };
    }, [elderId, session]),
  );

  async function saveAccount() {
    if (!elderId) {
      return;
    }
    setAccountMessage("");
    setAccountBusy(true);
    try {
      await setElderAccount(elderId, accountPhone, accountPassword, token);
      setAccountMessage(strings.elderDetail.accountSaved);
      setAccountPassword("");
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setAccountMessage(exc instanceof ApiError ? exc.message : strings.elderDetail.accountSaveFailed);
    } finally {
      setAccountBusy(false);
    }
  }

  async function makeInvite() {
    if (!elderId) {
      return;
    }
    setBusy(true);
    try {
      setInviteCode(await createGuardianInvite(elderId, token));
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setError(exc instanceof Error ? exc.message : strings.elderDetail.inviteFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <ErrorText message={error} />

      <Section title={strings.elderDetail.healthReportSection}>
        {report === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : (
          <View style={styles.reportBody}>
            {report.risk_events.length === 0 ? (
              <Text style={styles.ok}>{strings.elderDetail.noRiskEvents}</Text>
            ) : (
              report.risk_events.map((e, i) => (
                <Text key={`risk-${i}`} style={styles.risk}>
                  {formatTime(e.created_at)}｜{tierLabel(e.tier)}｜{e.reason}
                </Text>
              ))
            )}
            {report.reminders.length > 0 ? (
              <Text style={styles.soft}>{strings.elderDetail.remindersCount(report.reminders.length)}</Text>
            ) : null}
          </View>
        )}
      </Section>

      <Section title={strings.elderDetail.dailySummarySection}>
        {summaries === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : summaries.length === 0 ? (
          <EmptyHint text={strings.elderDetail.noSummaries} />
        ) : (
          summaries.map((s) => (
            <View key={s.date} style={styles.summaryItem}>
              <Text style={styles.summaryDate}>{s.date}</Text>
              <Text style={styles.row}>{s.content}</Text>
            </View>
          ))
        )}
      </Section>

      <Section title={strings.elderDetail.medicationsSection}>
        {medications.length === 0 ? (
          <EmptyHint text={strings.elderDetail.noMedications} />
        ) : (
          medications.map((m) => (
            <Text key={m.medication_id} style={styles.row}>
              {m.name}（{m.slots.map(slotLabel).join("、")}）
            </Text>
          ))
        )}
        <Button
          label={strings.elderDetail.manageMedications}
          variant="outline"
          onPress={() => router.push(`/guardian/elder/${elderId}/medications`)}
        />
      </Section>

      <Section title={strings.elderDetail.upcomingAppointmentsSection}>
        {appointments.length === 0 ? (
          <EmptyHint text={strings.elderDetail.noAppointments} />
        ) : (
          appointments.map((a) => (
            <Text key={a.appointment_id} style={styles.row}>
              {a.date}｜{a.label}
            </Text>
          ))
        )}
        <Button
          label={strings.elderDetail.manageAppointments}
          variant="outline"
          onPress={() => router.push(`/guardian/elder/${elderId}/appointments`)}
        />
      </Section>

      <Section title={strings.elderDetail.accountSection}>
        <Text style={styles.soft}>{strings.elderDetail.accountHelp}</Text>
        <Field
          label={strings.elderDetail.accountPhoneLabel}
          value={accountPhone}
          onChangeText={setAccountPhone}
          keyboardType="phone-pad"
          placeholder="09xxxxxxxx"
        />
        <Field
          label={strings.elderDetail.accountPasswordLabel}
          value={accountPassword}
          onChangeText={setAccountPassword}
          secureTextEntry
        />
        <Button
          label={strings.elderDetail.saveAccount}
          onPress={saveAccount}
          busy={accountBusy}
          variant="outline"
          disabled={!accountPhone.trim() || accountPassword.length < 8}
        />
        {accountMessage ? <Text style={styles.soft}>{accountMessage}</Text> : null}
      </Section>

      <Section title={strings.elderDetail.inviteSection}>
        <Button label={strings.elderDetail.makeInvite} onPress={makeInvite} busy={busy} variant="outline" />
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
  summaryItem: { gap: 2 },
  summaryDate: { fontSize: 14, color: colors.textSoft },
  inviteCode: { fontSize: 26, fontWeight: "800", color: colors.primary, letterSpacing: 1 },
});
