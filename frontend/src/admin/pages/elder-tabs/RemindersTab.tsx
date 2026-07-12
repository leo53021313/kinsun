import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import {
  type AdminElderReminders,
  dispatchReminder,
  getElderReminders,
  getMeta,
} from "../../api";
import { formatTime } from "../../format";

const SLOT_LABELS: Record<string, string> = {
  morning: "早上",
  noon: "中午",
  evening: "晚上",
  bedtime: "睡前",
};

/** 提醒設定分頁：用藥／回診主檔＋近期發送紀錄；內測模式可立即發送。 */
export function RemindersTab() {
  const { elderId } = useParams<{ elderId: string }>();
  const [data, setData] = useState<AdminElderReminders | null>(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    getElderReminders(elderId).then(setData, () => setError(true));
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
      setNotice("已觸發發送，可到時間軸或訊息流確認。");
      load();
    } catch {
      setNotice("觸發失敗，請確認內測模式是否開啟。");
    }
  }

  if (error) return <p className="error-banner">載入失敗，請重新整理。</p>;
  if (!data) return <p>載入中…</p>;
  return (
    <div>
      {notice && <p className="card">{notice}</p>}
      <h3>用藥設定</h3>
      {data.medications.length === 0 && <p>尚未設定用藥。</p>}
      {data.medications.map((m) => (
        <div className="card" key={m.medication_id}>
          <strong>{m.name}</strong>　時段：{m.slots.map((s) => SLOT_LABELS[s] ?? s).join("、")}
          {testing &&
            m.slots.map((s) => (
              <button key={s} type="button" onClick={() => send("medication", s)}>
                立即發送{SLOT_LABELS[s] ?? s}提醒（內測）
              </button>
            ))}
        </div>
      ))}
      <h3>回診設定</h3>
      {data.appointments.length === 0 && <p>尚未設定回診。</p>}
      {data.appointments.map((a) => (
        <div className="card" key={a.appointment_id}>
          <strong>{a.date}</strong>　{a.label}
        </div>
      ))}
      {testing && data.appointments.length > 0 && (
        <button type="button" onClick={() => send("appointment")}>
          立即發送今明兩天回診提醒（內測）
        </button>
      )}
      <h3>近期提醒發送紀錄</h3>
      {data.reminder_logs.length === 0 && <p>還沒有發送紀錄。</p>}
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
