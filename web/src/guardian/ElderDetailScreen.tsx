/** 長輩詳情：一頁分區塊，家屬要知道的事全在這裡。 */

import { formatTime } from "kinsun-shared/format";
import { tierLabel } from "kinsun-shared/terms";
import type { DailySummary, HealthReport, ScheduleGroup } from "kinsun-shared/types";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/api";
import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { Section } from "@/ui/Section";

import { createGuardianInvite, getHealthReport, listDailySummaries, listSchedules, setElderAccount } from "./api";
import { describeGroup } from "./schedules";

const MIN_PASSWORD_LENGTH = 8;

export function ElderDetailScreen(props: {
  elderId: string;
  elderName: string;
  onManageSchedules: () => void;
}) {
  const { elderId, elderName } = props;
  const { session, signOut } = GuardianSession.useSession();
  const token = session?.token ?? "";
  // ⚠️ 用 useMemo 而非 useCallback：makeSignOutOnAuthError 是**工廠**，回傳的是函式
  // 值，而 useCallback 收的應該是行內函式表達式——react-hooks 的規則會擋下來。
  // signOut 在 session 工廠裡是 useCallback([]) 的穩定參考，所以這個值也穩定，
  // 不會讓下面的 effect 反覆重打 API。
  const signOutOn401 = useMemo(() => makeSignOutOnAuthError(signOut), [signOut]);

  const [report, setReport] = useState<HealthReport | null>(null);
  const [summaries, setSummaries] = useState<DailySummary[] | null>(null);
  const [groups, setGroups] = useState<ScheduleGroup[] | null>(null);
  // 三個區塊各自的失敗旗標（非共用 error）：某一支端點失敗時，只有那個區塊要顯示
  // 錯誤，另外兩支已經成功回來的資料要照常顯示，不能被一支拖累。
  const [reportError, setReportError] = useState(false);
  const [summariesError, setSummariesError] = useState(false);
  const [groupsError, setGroupsError] = useState(false);
  const [error, setError] = useState("");

  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [accountMessage, setAccountMessage] = useState("");
  const [accountBusy, setAccountBusy] = useState(false);

  const [inviteCode, setInviteCode] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);

  useEffect(() => {
    if (!token) {
      return;
    }
    let alive = true;
    // 三支一起發、各自獨立降級：它們互不相依，逐支等會讓這一頁多兩趟往返的空白；
    // 用 allSettled 而非 all，是因為某一支失敗（例如逾時、500）不該連累另外兩支
    // 已經成功回來的資料——那樣會讓整頁卡在「載入中…」，看起來像系統當掉。
    Promise.allSettled([
      getHealthReport(elderId, token),
      listDailySummaries(elderId, token),
      listSchedules(elderId, token),
    ]).then(([hr, daily, schedules]) => {
      if (!alive) return;
      if (hr.status === "fulfilled") {
        setReport(hr.value);
      } else if (!signOutOn401(hr.reason)) {
        setReportError(true);
      }
      if (daily.status === "fulfilled") {
        setSummaries(daily.value);
      } else if (!signOutOn401(daily.reason)) {
        setSummariesError(true);
      }
      if (schedules.status === "fulfilled") {
        setGroups(schedules.value);
      } else if (!signOutOn401(schedules.reason)) {
        setGroupsError(true);
      }
    });
    return () => {
      alive = false;
    };
  }, [elderId, token, signOutOn401]);

  async function saveAccount() {
    setAccountMessage("");
    setAccountBusy(true);
    try {
      await setElderAccount(elderId, phone, password, token);
      setAccountMessage(strings.elderDetail.accountSaved);
      setPassword("");
    } catch (exc) {
      if (signOutOn401(exc)) return;
      // 後端的驗證訊息已經是繁中人話（D-24），直接顯示比自己重寫一句準確。
      setAccountMessage(
        exc instanceof ApiError ? exc.message : strings.elderDetail.accountSaveFailed,
      );
    } finally {
      setAccountBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <h1 className="text-lg font-bold text-ink">{elderName}</h1>
      <ErrorText message={error} />

      <Section title={strings.elderDetail.healthReportSection}>
        {reportError ? (
          <ErrorText message={strings.common.loadFailed} />
        ) : report === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : report.risk_events.length === 0 ? (
          <p className="text-sm text-success">{strings.elderDetail.noRiskEvents}</p>
        ) : (
          report.risk_events.map((event, index) => (
            <p key={index} className="text-sm text-danger">
              {formatTime(event.created_at)}
              {" "}
              <span aria-hidden>｜</span>
              {" "}
              {tierLabel(event.tier)}
              {" "}
              <span aria-hidden>｜</span>
              {" "}
              {event.reason}
            </p>
          ))
        )}
        {report && report.reminders.length > 0 ? (
          <p className="text-xs text-ink-soft">
            {strings.elderDetail.remindersCount(report.reminders.length)}
          </p>
        ) : null}
      </Section>

      <Section title={strings.elderDetail.dailySummarySection}>
        {summariesError ? (
          <ErrorText message={strings.common.loadFailed} />
        ) : summaries === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : summaries.length === 0 ? (
          <EmptyHint text={strings.elderDetail.noSummaries} />
        ) : (
          summaries.map((summary) => (
            <div key={summary.date} className="flex flex-col">
              <span className="text-xs text-ink-soft">{summary.date}</span>
              <span className="text-sm text-ink">{summary.content}</span>
            </div>
          ))
        )}
      </Section>

      <Section title={strings.elderDetail.schedulesSection}>
        {groupsError ? (
          <ErrorText message={strings.common.loadFailed} />
        ) : groups === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : groups.length === 0 ? (
          <EmptyHint text={strings.elderDetail.noSchedules} />
        ) : (
          groups.map((group) => (
            <div key={group.group_id} className="flex flex-col">
              <span className="text-sm text-ink">{describeGroup(group)}</span>
              {group.created_by === "elder" ? (
                <span className="text-xs text-ink-soft">{strings.schedules.byElder}</span>
              ) : null}
            </div>
          ))
        )}
        <Button
          label={strings.elderDetail.manageSchedules}
          variant="outline"
          onClick={props.onManageSchedules}
        />
      </Section>

      <Section title={strings.elderDetail.accountSection}>
        <p className="text-xs leading-5 text-ink-soft">{strings.elderDetail.accountHelp}</p>
        <Field
          label={strings.elderDetail.accountPhoneLabel}
          value={phone}
          onChange={setPhone}
          type="tel"
          placeholder={strings.elderDetail.accountPhonePlaceholder}
        />
        <Field
          label={strings.elderDetail.accountPasswordLabel}
          value={password}
          onChange={setPassword}
          type="password"
          autoComplete="new-password"
        />
        <Button
          label={strings.elderDetail.saveAccount}
          variant="outline"
          onClick={saveAccount}
          busy={accountBusy}
          disabled={!phone.trim() || password.length < MIN_PASSWORD_LENGTH}
        />
        {accountMessage ? <p className="text-xs text-ink-soft">{accountMessage}</p> : null}
      </Section>

      <Section title={strings.elderDetail.inviteSection}>
        <Button
          label={strings.elderDetail.makeInvite}
          variant="outline"
          busy={inviteBusy}
          onClick={async () => {
            setInviteBusy(true);
            try {
              setInviteCode(await createGuardianInvite(elderId, token));
            } catch (exc) {
              if (signOutOn401(exc)) return;
              setError(strings.elderDetail.inviteFailed);
            } finally {
              setInviteBusy(false);
            }
          }}
        />
        {inviteCode ? (
          <p className="text-2xl font-extrabold tracking-widest text-primary">{inviteCode}</p>
        ) : null}
      </Section>
    </div>
  );
}
