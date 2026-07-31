/** 長輩詳情：一頁分區塊，家屬要知道的事全在這裡。 */

import { formatTime } from "kinsun-shared/format";
import { tierLabel } from "kinsun-shared/terms";
import type { DailySummary, HealthReport, ScheduleGroup } from "kinsun-shared/types";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { ApiError } from "@/api";
import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText, NoticeText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { Section } from "@/ui/Section";

import {
  createGuardianInvite,
  getHealthReport,
  listDailySummaries,
  listSchedules,
  revokeElderDeviceBindings,
  setElderAccount,
} from "./api";
import { InviteCard } from "./InviteCard";
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
  // ⚠️ 成功與失敗**分成兩個狀態**、走兩種樣式。共用一個字串（且共用一個裸 <p> 灰
  // 色小字）時，「這個手機號碼已經幫另一位長輩註冊過了」（後端 409 phone_taken）
  // 會出現在跟「已設定完成。長輩手機用這組號碼＋密碼登入一次就會一直記住。」完全
  // 相同的位置與樣式——家屬據此判定設好了，接著拿那組帳密去長輩端登入吃 401，而
  // 家屬端沒有任何線索指出哪裡錯。同一頁其他所有錯誤都走 ErrorText，這裡不可例外。
  const [accountMessage, setAccountMessage] = useState("");
  const [accountError, setAccountError] = useState("");
  const [accountBusy, setAccountBusy] = useState(false);

  const [inviteCode, setInviteCode] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);

  // 長輩綁定碼的重取路徑。原本這組碼只活在 `HomeScreen` 建立長輩當下的暫態 state：
  // 家屬點進詳情頁一次，`HomeScreen` 卸載、碼歸零，返回後 `GET /elders` 的回應裡
  // 也沒有它——想配對長輩手機只剩「再建一位長輩」這條路，而那會留下一筆刪不掉的
  // 重複資料（後端沒有 DELETE /elders）。P3 更有三句錯誤訊息叫長輩「請家人重新
  // 產生一組」，在此之前那三句是死路。
  const [bindingCode, setBindingCode] = useState("");
  const [bindingError, setBindingError] = useState("");
  const [bindingBusy, setBindingBusy] = useState(false);
  // 二次確認：這是本頁破壞性最強的操作——長輩手機上的金孫會馬上被登出，而他自己
  // 不會知道發生什麼事，只會發現「金孫不理我了」；家屬按下去的當下，長輩甚至可能
  // 正在跟金孫講話。刪一筆排程都要確認，這個更要。
  //
  // ⚠️ 用畫面內的確認列而非瀏覽器的 confirm()：confirm 會鎖住整個分頁，左欄的長輩
  // 端連對講機都按不了——雙欄同時存在時，任何 modal 對話框都是全域的
  // （與 SchedulesScreen 的刪除確認列同一套作法與同一個理由）。
  const [isConfirmingBinding, setIsConfirmingBinding] = useState(false);
  const bindingConfirmHeadingId = useId();
  const bindingConfirmRef = useRef<HTMLDivElement | null>(null);

  // 確認列一出現就把焦點移進去：它在 DOM 裡但焦點沒過去的話，螢幕報讀軟體不會
  // 朗讀那句後果——而那句後果正是這顆按鈕存在的理由。
  useEffect(() => {
    if (isConfirmingBinding) {
      bindingConfirmRef.current?.focus();
    }
  }, [isConfirmingBinding]);

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
    setAccountError("");
    setAccountBusy(true);
    try {
      await setElderAccount(elderId, phone, password, token);
      setAccountMessage(strings.elderDetail.accountSaved);
      setPassword("");
    } catch (exc) {
      if (signOutOn401(exc)) return;
      // 後端的驗證訊息已經是繁中人話（D-24），直接顯示比自己重寫一句準確。
      setAccountError(
        exc instanceof ApiError ? exc.message : strings.elderDetail.accountSaveFailed,
      );
    } finally {
      setAccountBusy(false);
    }
  }

  async function regenerateBinding() {
    setBindingBusy(true);
    setBindingError("");
    try {
      setBindingCode(await revokeElderDeviceBindings(elderId, token));
      setIsConfirmingBinding(false);
    } catch (exc) {
      if (signOutOn401(exc)) return;
      // 確認列刻意留著：家屬可以直接再按一次「確定換新碼」，不必從頭再點一遍。
      setBindingError(strings.elderDetail.bindingFailed);
    } finally {
      setBindingBusy(false);
    }
  }

  /** 改了號碼或密碼就把上一次的結果清掉——舊的「已設定完成」掛在新輸入的號碼
   *  旁邊，家屬會以為新號碼也已經存好了；舊的錯誤同理，會蓋住他剛修正的內容。 */
  function editAccountField(setter: (value: string) => void) {
    return (value: string) => {
      setAccountMessage("");
      setAccountError("");
      setter(value);
    };
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

      <Section title={strings.schedules.listSection}>
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
          onChange={editAccountField(setPhone)}
          type="tel"
          placeholder={strings.elderDetail.accountPhonePlaceholder}
        />
        <Field
          label={strings.elderDetail.accountPasswordLabel}
          value={password}
          onChange={editAccountField(setPassword)}
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
        <NoticeText message={accountMessage} />
        <ErrorText message={accountError} />
      </Section>

      <Section title={strings.elderDetail.bindingSection}>
        <p className="text-xs leading-5 text-ink-soft">{strings.elderDetail.bindingHelp}</p>
        {/* 後果寫在按鈕上面、按下去之前就看得到；用 danger 色但不掛 role="alert"
            ——它是常駐的警語，不是剛剛發生的錯誤。 */}
        <p className="text-xs leading-5 text-danger">{strings.elderDetail.bindingWarning}</p>
        <Button
          label={strings.elderDetail.regenerateBinding}
          variant="outline"
          disabled={isConfirmingBinding}
          onClick={() => setIsConfirmingBinding(true)}
        />
        {isConfirmingBinding ? (
          <div
            ref={bindingConfirmRef}
            tabIndex={-1}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={bindingConfirmHeadingId}
            className="flex flex-col gap-2 rounded-2xl border-2 border-danger bg-surface p-4"
          >
            <p id={bindingConfirmHeadingId} className="text-sm text-ink">
              {strings.elderDetail.confirmRegenerateBinding}
            </p>
            <div className="flex gap-2">
              <Button
                label={strings.elderDetail.confirmRegenerateBindingButton}
                onClick={regenerateBinding}
                busy={bindingBusy}
              />
              <Button
                label={strings.common.cancel}
                variant="outline"
                disabled={bindingBusy}
                onClick={() => setIsConfirmingBinding(false)}
              />
            </div>
          </div>
        ) : null}
        {bindingCode ? <InviteCard code={bindingCode} /> : null}
        <ErrorText message={bindingError} />
      </Section>

      <Section title={strings.elderDetail.inviteSection}>
        <Button
          label={strings.elderDetail.makeInvite}
          variant="outline"
          busy={inviteBusy}
          onClick={async () => {
            setInviteBusy(true);
            // 重試前先清掉上一次的失敗：不清的話，頁面最上方掛著紅字「產生邀請碼
            // 失敗」，下方同時顯示一組有效的邀請碼，家屬不知道該相信哪一個。
            setError("");
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
