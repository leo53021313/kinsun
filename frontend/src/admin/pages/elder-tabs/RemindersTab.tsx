import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import {
  type AdminElderReminders,
  dispatchReminder,
  getElderReminders,
  getMeta,
} from "../../api";
import { formatTime } from "../../format";
import { strings } from "../../strings";

/** 提醒設定分頁：用藥／回診主檔＋近期發送紀錄；內測模式可立即發送。 */
export function RemindersTab() {
  const reminders = strings.elderTabs.reminders;
  const { elderId } = useParams<{ elderId: string }>();
  const [data, setData] = useState<AdminElderReminders | null>(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    if (!elderId) return;
    // setError(false) 放進成功處理器：開頭的同步 setState 會在 useEffect 中
    // 觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    getElderReminders(elderId).then(
      (data) => {
        setData(data);
        setError(false);
      },
      () => setError(true),
    );
  }, [elderId]);

  useEffect(load, [load]);
  useEffect(() => {
    getMeta().then(
      (m) => setTesting(m.internal_testing),
      () => setTesting(false),
    );
  }, []);

  async function send(kind: "medication" | "appointment", slot?: string) {
    if (!elderId) return;
    setNotice("");
    try {
      await dispatchReminder(elderId, { kind, slot });
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
      <h3>{reminders.medicationHeading}</h3>
      {data.medications.length === 0 && <p>{reminders.noMedications}</p>}
      {data.medications.map((m) => (
        <div className="card" key={m.medication_id}>
          <strong>{m.name}</strong>　{reminders.slotsPrefix}
          {m.slots.map((s) => reminders.slotLabels[s] ?? s).join("、")}
          {testing &&
            m.slots.map((s) => (
              <button key={s} type="button" onClick={() => send("medication", s)}>
                {reminders.sendSlotButton(reminders.slotLabels[s] ?? s)}
              </button>
            ))}
        </div>
      ))}
      <h3>{reminders.appointmentHeading}</h3>
      {data.appointments.length === 0 && <p>{reminders.noAppointments}</p>}
      {data.appointments.map((a) => (
        <div className="card" key={a.appointment_id}>
          <strong>
            {a.date}
            {a.time ? ` ${a.time}` : ""}
          </strong>
          　{a.label}
        </div>
      ))}
      {testing && data.appointments.length > 0 && (
        <button type="button" onClick={() => send("appointment")}>
          {reminders.sendAppointmentButton}
        </button>
      )}
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
