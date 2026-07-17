import { useCallback, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getTimeline } from "../api";
import { formatClock } from "../format";
import { strings } from "../strings";
import { useLoadable } from "../useLoadable";
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
  const {
    data: timeline,
    error,
    reload: load,
  } = useLoadable(useCallback(() => (elderId ? getTimeline(elderId, date) : null), [elderId, date]));

  return (
    <section>
      <h2>{timeline ? strings.timeline.title(timeline.name) : strings.timeline.fallbackTitle}</h2>
      <div className="card">
        <label>
          {strings.timeline.dateLabel}
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <button type="button" onClick={load}>
          {strings.common.refresh}
        </button>
      </div>
      {error && <p className="error-banner">{strings.common.loadFailedRefresh}</p>}
      {timeline && timeline.items.length === 0 && <p>{strings.timeline.noRecords}</p>}
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
                {strings.timeline.voice}（
                {item.role === "user" ? strings.common.roleElder : strings.common.roleAssistant}）
              </span>
              {item.content && <span>{item.content}</span>}
              {item.audio_url && <audio controls src={item.audio_url} preload="none" />}
              {item.trace_id && <Link to={`/traces/${item.trace_id}`}>{strings.common.viewTrace}</Link>}
            </div>
          )}
          {item.kind === "reminder" && (
            <div className="card timeline-item">
              <span className="timeline-time">{formatClock(item.created_at)}</span>
              <span className="badge badge-reminder">{strings.timeline.reminderBadge}</span>
              <span>{item.content}</span>
            </div>
          )}
          {item.kind === "risk" && (
            <div className="card timeline-item">
              <span className="timeline-time">{formatClock(item.created_at)}</span>
              <span className="badge badge-risk">
                {strings.timeline.riskPrefix} {adminTierLabel(item.tier ?? 0)}
              </span>
              <span>{item.content}</span>
              {item.trace_id && <Link to={`/traces/${item.trace_id}`}>{strings.common.viewTrace}</Link>}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
