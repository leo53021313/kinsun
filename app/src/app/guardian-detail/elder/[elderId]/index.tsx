import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import {
  ApiError,
  createGuardianInvite,
  getHealthReport,
  listDailySummaries,
  listSchedules,
  setElderAccount,
  type DailySummary,
  type HealthReport,
  type ScheduleGroup,
} from "@/lib/api";
import { describeGroup } from "@/lib/schedules";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { formatTime } from "kinsun-shared/format";
import { tierLabel } from "kinsun-shared/terms";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

/** 長輩詳情：用藥／回診／健康報告／家屬邀請碼，單頁分區塊。 */
export default function ElderDetail() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const [schedules, setSchedules] = useState<ScheduleGroup[]>([]);
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

  // useFocusEffect：從行程管理頁返回時重載，畫面才會反映剛做的編輯。
  useFocusEffect(
    useCallback(() => {
      if (!session || !elderId) {
        return;
      }
      let alive = true;
      (async () => {
        try {
          const [groups, hr, daily] = await Promise.all([
            listSchedules(elderId, session.token),
            getHealthReport(elderId, session.token),
            listDailySummaries(elderId, session.token),
          ]);
          if (alive) {
            setSchedules(groups);
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
    }, [elderId, session, signOutOn401]),
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
        {summaries && summaries.length > 0 ? (
          <Button
            label={strings.elderDetail.viewDailySummaries}
            variant="outline"
            onPress={() =>
              router.push({
                pathname: "/guardian-detail/elder/[elderId]/summary",
                params: { elderId },
              })
            }
          />
        ) : null}
      </Section>

      <Section title={strings.elderDetail.schedulesSection}>
        {schedules.length === 0 ? (
          <EmptyHint text={strings.elderDetail.noSchedules} />
        ) : (
          schedules.map((g) => (
            <Text key={g.group_id} style={styles.row}>
              {describeGroup(g)}
            </Text>
          ))
        )}
        <Button
          label={strings.elderDetail.manageSchedules}
          variant="outline"
              onPress={() =>
                router.push({
                  pathname: "/guardian-detail/elder/[elderId]/schedules",
                  params: { elderId },
                })
              }
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
  // ⚠️ 文字一律用深一階（規則 15）：`colors.success` 對白底只有 2.45:1、
  // `colors.danger` 3.70:1，兩者都是給邊界與圖示用的，當正文一律不合格。
  ok: { fontSize: 16, color: colors.successText },
  risk: { fontSize: 16, color: colors.dangerText },
  soft: { fontSize: 14, color: colors.textSoft },
  row: { fontSize: 17, color: colors.text },
  summaryItem: { gap: 2 },
  summaryDate: { fontSize: 14, color: colors.textSoft },
  inviteCode: { fontSize: 26, fontWeight: "800", color: colors.primary, letterSpacing: 1 },
});
