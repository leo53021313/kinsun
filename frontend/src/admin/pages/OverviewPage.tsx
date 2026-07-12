import { useState } from "react";

import { type Overview, getOverview } from "../api";
import { formatLatency, formatTime } from "../format";
import { strings } from "../strings";
import { usePolling } from "../usePolling";

function HourlyChart({ data }: { data: Overview["hourly_turns"] }) {
  const width = 720;
  const height = 160;
  const barGap = 4;
  if (data.length === 0) return <p>{strings.overview.noRecentMessages}</p>;
  const max = Math.max(...data.map((d) => d.turn_count));
  const barWidth = width / data.length - barGap;
  return (
    <svg
      viewBox={`0 0 ${width} ${height + 20}`}
      role="img"
      aria-label={strings.overview.hourlyChartAriaLabel}
      style={{ width: "100%", height: "auto" }}
    >
      {data.map((d, i) => {
        const barHeight = max === 0 ? 0 : (d.turn_count / max) * height;
        const x = i * (barWidth + barGap);
        const hour = new Date(d.hour_start * 1000).getHours();
        return (
          <g key={d.hour_start}>
            <rect
              x={x}
              y={height - barHeight}
              width={barWidth}
              height={barHeight}
              fill="#3b82f6"
            >
              <title>{strings.overview.hourBarTitle(hour, d.turn_count)}</title>
            </rect>
            <text x={x + barWidth / 2} y={height + 14} fontSize="10" textAnchor="middle">
              {hour}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [disconnected, setDisconnected] = useState(false);

  usePolling(async () => {
    try {
      setOverview(await getOverview());
      setDisconnected(false);
    } catch {
      setDisconnected(true);
    }
  }, 5000);

  if (overview === null) {
    return disconnected ? (
      <p className="error-banner">{strings.common.disconnected}</p>
    ) : (
      <p>{strings.common.loading}</p>
    );
  }
  return (
    <section>
      <h2>{strings.overview.title}</h2>
      {disconnected && <p className="error-banner">{strings.common.disconnected}</p>}
      {(overview.alerts ?? []).map((a) => (
        <p key={a.kind} className="error-banner">
          {a.kind === "guardian_notification_failure"
            ? strings.overview.guardianNotificationFailure(a.window_minutes, a.count)
            : strings.overview.riskClassifierFailure(a.window_minutes, a.count)}
        </p>
      ))}
      <div className="stat-grid">
        <div className="card">
          <div>{strings.overview.statTurnCount}</div>
          <div className="stat-value">{overview.turn_count}</div>
        </div>
        <div className="card">
          <div>{strings.overview.statActiveElders}</div>
          <div className="stat-value">{overview.active_elder_count}</div>
        </div>
        <div className="card">
          <div>{strings.overview.statRiskEvents}</div>
          <div className="stat-value">{overview.risk_event_count}</div>
        </div>
        <div className="card">
          <div>{strings.overview.statLlmTokens}</div>
          <div className="stat-value">
            {overview.llm_input_tokens}／{overview.llm_output_tokens}
          </div>
        </div>
      </div>
      <div className="card">
        <h3>{strings.overview.stagesHeading}</h3>
        <table>
          <thead>
            <tr>
              <th>{strings.overview.stageColumns.stage}</th>
              <th>{strings.overview.stageColumns.count}</th>
              <th>{strings.overview.stageColumns.error}</th>
              <th>{strings.overview.stageColumns.avgLatency}</th>
              <th>{strings.overview.stageColumns.p50Latency}</th>
              <th>{strings.overview.stageColumns.p95Latency}</th>
            </tr>
          </thead>
          <tbody>
            {overview.stages.map((s) => (
              <tr key={s.stage}>
                <td>{strings.overview.stageLabel[s.stage] ?? s.stage}</td>
                <td>{s.call_count}</td>
                <td>{s.error_count}</td>
                <td>{formatLatency(Math.round(s.avg_latency_ms))}</td>
                <td>{formatLatency(Math.round(s.p50_latency_ms))}</td>
                <td>{formatLatency(Math.round(s.p95_latency_ms))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>{strings.overview.hourlyHeading}</h3>
        <HourlyChart data={overview.hourly_turns} />
      </div>
      <p className="feed-time">
        {strings.overview.updatedAtPrefix} {formatTime(overview.generated_at)}
      </p>
    </section>
  );
}
