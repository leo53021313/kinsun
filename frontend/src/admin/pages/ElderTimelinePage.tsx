import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { type Timeline, getTimeline } from "../api";
import { formatClock } from "../format";
import { adminTierLabel } from "kinsun-shared/terms";

function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export function ElderTimelinePage() {
  const { elderId } = useParams<{ elderId: string }>();
  const [date, setDate] = useState(today());
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    getTimeline(elderId, date).then(setTimeline, () => setError(true));
  }, [elderId, date]);

  useEffect(load, [load]);

  return (
    <section>
      <h2>{timeline ? `${timeline.name} 的時間軸` : "長輩時間軸"}</h2>
      <div className="card">
        <label>
          日期：
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <button type="button" onClick={load}>
          重新整理
        </button>
      </div>
      {error && <p className="error-banner">載入失敗，請重新整理。</p>}
      {timeline && timeline.items.length === 0 && <p>這一天沒有任何紀錄。</p>}
      {timeline?.items.map((item, index) => (
        <div key={`${item.kind}-${item.created_at}-${index}`}>
          {item.kind === "turn" && (
            <div className={item.role === "user" ? "bubble-user" : "bubble-assistant"}>
              <span className="timeline-time">{formatClock(item.created_at)}</span>{" "}
              {item.content}
            </div>
          )}
          {item.kind === "voice" && (
            <div className="card timeline-item">
              <span className="timeline-time">{formatClock(item.created_at)}</span>
              <span className="badge badge-voice">
                語音（{item.role === "user" ? "長輩" : "金孫"}）
              </span>
              {item.content && <span>{item.content}</span>}
              {item.audio_url && <audio controls src={item.audio_url} preload="none" />}
              {item.trace_id && <Link to={`/traces/${item.trace_id}`}>檢視鏈路</Link>}
            </div>
          )}
          {item.kind === "reminder" && (
            <div className="card timeline-item">
              <span className="timeline-time">{formatClock(item.created_at)}</span>
              <span className="badge badge-reminder">推播</span>
              <span>{item.content}</span>
            </div>
          )}
          {item.kind === "risk" && (
            <div className="card timeline-item">
              <span className="timeline-time">{formatClock(item.created_at)}</span>
              <span className="badge badge-risk">風險 {adminTierLabel(item.tier ?? 0)}</span>
              <span>{item.content}</span>
              {item.trace_id && <Link to={`/traces/${item.trace_id}`}>檢視鏈路</Link>}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
