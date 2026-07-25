import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import type { AdminSchedule } from "kinsun-shared/types";

import { dispatchReminder, getElderReminders, getMeta } from "../../api";
import { formatTime } from "../../format";
import { strings } from "../../strings";
import { useLoadable } from "../../useLoadable";

/** 提醒設定分頁：統一排程清單＋近期發送紀錄（D-76 P5）；內測模式可立即發送。 */
export function RemindersTab() {
  const reminders = strings.elderTabs.reminders;
  const { elderId } = useParams<{ elderId: string }>();
  const {
    data,
    error,
    reload: load,
  } = useLoadable(useCallback(() => (elderId ? getElderReminders(elderId) : null), [elderId]));
  const [testing, setTesting] = useState(false);
  // notice 與載入無關（它是「已發送」之類的操作回饋），故不收進 hook。
  const [notice, setNotice] = useState("");

  useEffect(() => {
    getMeta().then(
      (m) => setTesting(m.internal_testing),
      () => setTesting(false),
    );
  }, []);

  async function send(kind: "medication" | "appointment" | "custom") {
    if (!elderId) return;
    setNotice("");
    try {
      await dispatchReminder(elderId, { kind });
      setNotice(reminders.dispatchTriggered);
      load();
    } catch {
      setNotice(reminders.dispatchFailed);
    }
  }

  if (error) return <p className="error-banner">{strings.common.loadFailedRefresh}</p>;
  if (!data) return <p>{strings.common.loading}</p>;
  return (
    <div>
      {notice && <p className="card">{notice}</p>}
      <h3>{reminders.scheduleHeading}</h3>
      {data.schedules.length === 0 && <p>{reminders.noSchedules}</p>}
      {data.schedules.map((s) => (
        <div className="card" key={s.schedule_id}>
          <span className="badge badge-reminder">{reminders.kindLabels[s.kind] ?? s.kind}</span>
          <strong>{s.title}</strong>　{describeAlarm(s)}
          {/* 長輩自己用說的建的也在這裡，標出來才知道那不是家屬設的。 */}
          {s.created_by === "elder" && <span>（{reminders.byElder}）</span>}
        </div>
      ))}
      {testing &&
        ["medication", "appointment", "custom"].map((kind) => (
          <button key={kind} type="button" onClick={() => send(kind as "medication")}>
            {reminders.sendKindButton(reminders.kindLabels[kind] ?? kind)}
          </button>
        ))}
      <h3>{reminders.logsHeading}</h3>
      {data.reminder_logs.length === 0 && <p>{reminders.noLogs}</p>}
      {data.reminder_logs.map((l, i) => (
        <div className="card timeline-item" key={`${l.created_at}-${i}`}>
          <span className="timeline-time">{formatTime(l.created_at)}</span>
          <span className="badge badge-reminder">{l.kind}</span>
          <span>{l.content}</span>
        </div>
      ))}
    </div>
  );
}

/** 一個鬧鐘的時間講法。後台是給值班的人看的，直接印絕對值不做白話包裝。 */
function describeAlarm(schedule: AdminSchedule): string {
  if (schedule.repeat === "daily") return `每天 ${schedule.time}`;
  if (schedule.repeat === "weekly") {
    const weekday = schedule.weekday === null ? "?" : "一二三四五六日"[schedule.weekday];
    return `每週${weekday} ${schedule.time}`;
  }
  return schedule.scheduled_at === null ? "—" : formatTime(schedule.scheduled_at);
}
