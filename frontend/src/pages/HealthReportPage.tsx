import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { type ReminderItem, type RiskEventItem, getHealthReport } from "../api";
import { formatTime, kindLabel, tierLabel } from "../report";

type Report = { risk_events: RiskEventItem[]; reminders: ReminderItem[] };

export function HealthReportPage() {
  const { elderId = "" } = useParams();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealthReport(elderId)
      .then(setReport)
      .catch(() => setError("載入失敗，請稍後再試"));
  }, [elderId]);

  if (error) return <p>{error}</p>;
  if (!report) return <p>載入中…</p>;
  return (
    <main>
      <p>
        <Link to="/">← 返回長輩清單</Link>
      </p>
      <h1>健康報告（近 30 天）</h1>
      <h2>危急事件</h2>
      {report.risk_events.length === 0 ? (
        <p>近 30 天無危急事件</p>
      ) : (
        <ul>
          {report.risk_events.map((e, i) => (
            <li key={i}>
              {formatTime(e.created_at)} · {tierLabel(e.tier)} · {e.reason}
            </li>
          ))}
        </ul>
      )}
      <h2>提醒紀錄</h2>
      {report.reminders.length === 0 ? (
        <p>近 30 天無提醒紀錄</p>
      ) : (
        <ul>
          {report.reminders.map((r, i) => (
            <li key={i}>
              {formatTime(r.created_at)} · {kindLabel(r.kind)} · {r.content}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
