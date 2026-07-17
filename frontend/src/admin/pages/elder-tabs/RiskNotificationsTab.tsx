import { useCallback } from "react";
import { useParams } from "react-router-dom";

import { type AdminRiskNotification, listElderRiskNotifications } from "../../api";
import { formatTime } from "../../format";
import { strings } from "../../strings";
import { useLoadable } from "../../useLoadable";
import { adminTierLabel } from "kinsun-shared/terms";

/** 送達語意（✅ 庚-16）：推播未上線前，App 通道僅為「落庫待拉取」而非真送達——
 * 只走 App 的成功要誠實顯示「已入通知匣（待開啟）」，避免維運誤信家屬已收到。 */
function deliveryLabel(n: AdminRiskNotification): string {
  if (!n.delivered) return strings.elderTabs.risk.deliveryFailed;
  if (n.channels && !n.channels.split(",").includes("line")) {
    return strings.elderTabs.risk.deliveryInbox;
  }
  return strings.elderTabs.risk.deliveryDelivered;
}

/** 危急通知分頁：每次危急事件通知了哪些家屬、每一位成功還是失敗。 */
export function RiskNotificationsTab() {
  const { elderId } = useParams<{ elderId: string }>();
  const { data: items, error } = useLoadable(
    useCallback(() => (elderId ? listElderRiskNotifications(elderId) : null), [elderId]),
  );

  if (error) return <p className="error-banner">{strings.common.loadFailedRefresh}</p>;
  if (!items) return <p>{strings.common.loading}</p>;
  return (
    <div>
      <h3>{strings.elderTabs.risk.heading}</h3>
      {items.length === 0 && <p>{strings.elderTabs.risk.noNotifications}</p>}
      {items.map((n, i) => (
        <div className="card timeline-item" key={`${n.created_at}-${i}`}>
          <span className="timeline-time">{formatTime(n.created_at)}</span>
          <span className="badge badge-risk">{adminTierLabel(n.tier)}</span>
          <span>
            {strings.elderTabs.risk.notifyPrefix} {n.guardian_name}
          </span>
          <span className={`badge ${n.delivered ? "badge-ok" : "badge-error"}`}>
            {deliveryLabel(n)}
          </span>
        </div>
      ))}
    </div>
  );
}
