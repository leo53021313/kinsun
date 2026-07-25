import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { type ReminderItem, type RiskEventItem, getHealthReport } from "../api";
import { formatTime, kindLabel, tierLabel } from "../report";
import { strings } from "../strings";

type Report = { risk_events: RiskEventItem[]; reminders: ReminderItem[] };

export function HealthReportPage() {
  const { elderId = "" } = useParams();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealthReport(elderId)
      .then(setReport)
      .catch(() => setError(strings.common.loadFailed));
  }, [elderId]);

  if (error) return <p>{error}</p>;
  if (!report) return <p>{strings.common.loading}</p>;
  return (
    <main>
      <p>
        <Link to="/">{strings.common.backToElders}</Link>
      </p>
      <h1>{strings.healthReport.title}</h1>
      <h2>{strings.healthReport.riskEventsHeading}</h2>
      {report.risk_events.length === 0 ? (
        <p>{strings.healthReport.noRiskEvents}</p>
      ) : (
        <ul>
          {report.risk_events.map((e, i) => (
            <li key={i}>
              {formatTime(e.created_at)} · {tierLabel(e.tier)} · {e.reason}
            </li>
          ))}
        </ul>
      )}
      <h2>{strings.healthReport.remindersHeading}</h2>
      {report.reminders.length === 0 ? (
        <p>{strings.healthReport.noReminders}</p>
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
