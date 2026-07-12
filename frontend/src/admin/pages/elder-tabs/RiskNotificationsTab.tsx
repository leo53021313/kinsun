import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { type AdminRiskNotification, listElderRiskNotifications } from "../../api";
import { formatTime } from "../../format";

/** 送達語意（✅ 庚-16）：推播未上線前，App 通道僅為「落庫待拉取」而非真送達——
 * 只走 App 的成功要誠實顯示「已入通知匣（待開啟）」，避免維運誤信家屬已收到。 */
function deliveryLabel(n: AdminRiskNotification): string {
  if (!n.delivered) return "失敗";
  if (n.channels && !n.channels.split(",").includes("line")) return "已入通知匣（待開啟）";
  return "送達";
}

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
            {deliveryLabel(n)}
          </span>
        </div>
      ))}
    </div>
  );
}
