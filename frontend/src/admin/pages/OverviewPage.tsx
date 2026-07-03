import { useState } from "react";

import { type Overview, getOverview } from "../api";
import { formatLatency, formatTime } from "../format";
import { usePolling } from "../usePolling";

const STAGE_LABEL: Record<string, string> = { asr: "ASR", llm: "LLM", tts: "TTS" };

function HourlyChart({ data }: { data: Overview["hourly_turns"] }) {
  const width = 720;
  const height = 160;
  const barGap = 4;
  if (data.length === 0) return <p>近 24 小時沒有訊息。</p>;
  const max = Math.max(...data.map((d) => d.turn_count));
  const barWidth = width / data.length - barGap;
  return (
    <svg
      viewBox={`0 0 ${width} ${height + 20}`}
      role="img"
      aria-label="近 24 小時逐時訊息量"
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
              <title>{`${hour} 時：${d.turn_count} 則`}</title>
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
    return disconnected ? <p className="error-banner">連線中斷，重試中…</p> : <p>載入中…</p>;
  }
  return (
    <section>
      <h2>總覽儀表板</h2>
      {disconnected && <p className="error-banner">連線中斷，重試中…</p>}
      <div className="stat-grid">
        <div className="card">
          <div>今日訊息量</div>
          <div className="stat-value">{overview.turn_count}</div>
        </div>
        <div className="card">
          <div>活躍長輩</div>
          <div className="stat-value">{overview.active_elder_count}</div>
        </div>
        <div className="card">
          <div>風險事件</div>
          <div className="stat-value">{overview.risk_event_count}</div>
        </div>
        <div className="card">
          <div>LLM token（入／出）</div>
          <div className="stat-value">
            {overview.llm_input_tokens}／{overview.llm_output_tokens}
          </div>
        </div>
      </div>
      <div className="card">
        <h3>各階段今日狀況</h3>
        <table>
          <thead>
            <tr>
              <th>階段</th>
              <th>次數</th>
              <th>錯誤</th>
              <th>平均延遲</th>
              <th>p95 延遲</th>
            </tr>
          </thead>
          <tbody>
            {overview.stages.map((s) => (
              <tr key={s.stage}>
                <td>{STAGE_LABEL[s.stage] ?? s.stage}</td>
                <td>{s.call_count}</td>
                <td>{s.error_count}</td>
                <td>{formatLatency(Math.round(s.avg_latency_ms))}</td>
                <td>{formatLatency(Math.round(s.p95_latency_ms))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>近 24 小時訊息量</h3>
        <HourlyChart data={overview.hourly_turns} />
      </div>
      <p className="feed-time">更新於 {formatTime(overview.generated_at)}</p>
    </section>
  );
}
