import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { type AdminRiskNotification, listElderRiskNotifications } from "../../api";
import { formatTime } from "../../format";

/** 危急通知分頁：每次危急事件通知了哪些家屬、每一位成功還是失敗。 */
export function RiskNotificationsTab() {
  const { elderId } = useParams<{ elderId: string }>();
  const [items, setItems] = useState<AdminRiskNotification[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    listElderRiskNotifications(elderId).then(setItems, () => setError(true));
  }, [elderId]);

  useEffect(load, [load]);

  if (error) return <p className="error-banner">載入失敗，請重新整理。</p>;
  if (!items) return <p>載入中…</p>;
  return (
    <div>
      <h3>危急通知送達紀錄（每位家屬一筆）</h3>
      {items.length === 0 && <p>還沒有危急通知。</p>}
      {items.map((n, i) => (
        <div className="card timeline-item" key={`${n.created_at}-${i}`}>
          <span className="timeline-time">{formatTime(n.created_at)}</span>
          <span className="badge badge-risk">L{n.tier}</span>
          <span>通知 {n.guardian_name}</span>
          <span className={`badge ${n.delivered ? "badge-ok" : "badge-error"}`}>
            {n.delivered ? "送達" : "失敗"}
          </span>
        </div>
      ))}
    </div>
  );
}
