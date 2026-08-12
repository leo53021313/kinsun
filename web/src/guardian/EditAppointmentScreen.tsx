/**
 * 改回診時間（W6）：只送現有 `ScheduleInput` 真正支援的日期與時間。
 *
 * ⚠️ 交付稿還畫了「誰帶長輩去」與「讓阿白告訴長輩改了」兩個控制項，**這裡不做**：
 * `ScheduleInput`（`shared/types.ts`）沒有 `driver` 與 `notify_elder`，後端也沒有。
 * 那是設計稿與真實契約的矛盾，不是實作漏做——畫上去只會送出後端收不到的欄位，或
 * 更糟，讓家屬以為長輩會被告知而其實不會。App 那批也是同樣的處理。
 *
 * ⚠️ 刪除的二次確認用**畫面內的確認列**，不用 `window.confirm`：後者會鎖住整個
 * 分頁，雙欄同時存在時另一欄連按都按不了（同 `elder/TalkScreen` 的登出確認）。
 */

import { useCallback, useEffect, useState } from "react";

import type { ScheduleGroup } from "kinsun-shared/types";

import { ApiError } from "@/api";
import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { Section } from "@/ui/Section";

import { deleteSchedule, listSchedules, updateSchedule } from "./api";
import { formatAppointmentWhen } from "./guardianFormat";
import { toOccurrences } from "./schedules";

type BusyAction = "save" | "delete" | null;

export function EditAppointmentScreen(props: {
  elderId: string;
  scheduleId: string;
  /** 存檔或刪除成功後回上一頁。 */
  onDone: () => void;
}) {
  const { elderId, scheduleId, onDone } = props;
  const { session, signOut } = GuardianSession.useSession();
  const [schedule, setSchedule] = useState<ScheduleGroup | null>(null);
  const [when, setWhen] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const token = session?.token ?? "";

  useEffect(() => {
    if (!token) return;
    const signOutOn401 = makeSignOutOnAuthError(signOut);
    let alive = true;
    void (async () => {
      try {
        const groups = await listSchedules(elderId, token, "appointment");
        const found = groups.find((group) => group.group_id === scheduleId) ?? null;
        if (alive) {
          setSchedule(found);
          setWhen(found ? formatAppointmentWhen(found.event_at) : "");
          if (!found) setError(strings.editAppointment.notFound);
        }
      } catch (exc) {
        if (signOutOn401(exc)) return;
        if (alive) setError(strings.common.loadFailed);
      } finally {
        if (alive) setLoaded(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [elderId, scheduleId, token, signOut]);

  const save = useCallback(async () => {
    if (!token || !schedule) return;
    const built = toOccurrences("appointment", { slots: [], when });
    if (!built) {
      // 先擋在前端：時間格式不對就不必往返一趟。
      setError(strings.editAppointment.invalidWhen);
      return;
    }
    setError("");
    setBusyAction("save");
    try {
      await updateSchedule(
        elderId,
        schedule.group_id,
        { kind: "appointment", title: schedule.title, ...built },
        token,
      );
      onDone();
    } catch (exc) {
      if (makeSignOutOnAuthError(signOut)(exc)) return;
      setError(exc instanceof ApiError ? exc.message : strings.common.saveFailed);
    } finally {
      setBusyAction(null);
    }
  }, [elderId, onDone, schedule, signOut, token, when]);

  const remove = useCallback(async () => {
    if (!token || !schedule) return;
    setError("");
    setIsConfirmingDelete(false);
    setBusyAction("delete");
    try {
      await deleteSchedule(elderId, schedule.group_id, token);
      onDone();
    } catch (exc) {
      if (makeSignOutOnAuthError(signOut)(exc)) return;
      setError(exc instanceof ApiError ? exc.message : strings.common.deleteFailed);
    } finally {
      setBusyAction(null);
    }
  }, [elderId, onDone, schedule, signOut, token]);

  if (!loaded) {
    return (
      <div className="p-4">
        <EmptyHint text={strings.common.loading} />
      </div>
    );
  }

  if (!schedule) {
    return (
      <div className="p-4">
        <ErrorText message={error || strings.editAppointment.notFound} />
      </div>
    );
  }

  const isBusy = busyAction !== null;

  return (
    <div className="flex flex-col gap-5 p-4">
      <Section title={schedule.title}>
        <Field
          label={strings.editAppointment.whenLabel}
          value={when}
          onChange={setWhen}
          placeholder={strings.schedules.whenPlaceholder("appointment")}
          hint={strings.editAppointment.whenHint}
        />
      </Section>

      <p className="text-base leading-relaxed text-ink-soft">
        {strings.editAppointment.savedEffect}
      </p>

      <ErrorText message={error} />

      <Button
        label={strings.editAppointment.save}
        onClick={() => void save()}
        busy={busyAction === "save"}
        disabled={isBusy}
      />

      {isConfirmingDelete ? (
        <div
          role="alertdialog"
          aria-label={strings.editAppointment.deleteThis}
          className="flex flex-col gap-3 rounded-card border-2 border-danger bg-surface p-4"
        >
          <p className="text-base leading-relaxed text-ink">
            {strings.editAppointment.deleteConfirm(schedule.title)}
          </p>
          <div className="flex gap-2">
            <Button
              label={strings.common.delete}
              variant="danger"
              onClick={() => void remove()}
              busy={busyAction === "delete"}
              disabled={isBusy}
            />
            <Button
              label={strings.common.cancel}
              variant="outline"
              onClick={() => setIsConfirmingDelete(false)}
              disabled={isBusy}
            />
          </div>
        </div>
      ) : (
        <Button
          label={strings.editAppointment.deleteThis}
          variant="danger"
          onClick={() => setIsConfirmingDelete(true)}
          disabled={isBusy}
        />
      )}
    </div>
  );
}
