import { useCallback, useEffect, useState } from "react";

import { type AdminJob, getMeta, listJobs, runJob } from "../api";
import { formatTime } from "../format";
import { strings } from "../strings";

/** 系統頁（spec 2026-07-12 §3.3–3.4）：排程任務狀態；內測模式可立即執行。 */
export function SystemPage() {
  const [jobs, setJobs] = useState<AdminJob[] | null>(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState("");
  const [busyJob, setBusyJob] = useState("");

  const load = useCallback(() => {
    setError(false);
    listJobs().then(setJobs, () => setError(true));
  }, []);

  useEffect(load, [load]);
  useEffect(() => {
    getMeta().then(
      (m) => setTesting(m.internal_testing),
      () => setTesting(false),
    );
  }, []);

  async function run(jobName: string) {
    setNotice("");
    setBusyJob(jobName);
    try {
      await runJob(jobName);
      setNotice(strings.system.jobExecuted(jobName));
      load();
    } catch {
      setNotice(strings.system.runFailed);
    } finally {
      setBusyJob("");
    }
  }

  if (error) return <p className="error-banner">{strings.common.loadFailedRefresh}</p>;
  if (!jobs) return <p>{strings.common.loading}</p>;
  return (
    <section>
      <h2>{strings.system.title}</h2>
      {notice && <p className="card">{notice}</p>}
      <table className="jobs-table">
        <thead>
          <tr>
            <th>{strings.system.columns.job}</th>
            <th>{strings.system.columns.cron}</th>
            <th>{strings.system.columns.lastRun}</th>
            {testing && <th>{strings.system.columns.action}</th>}
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.job_name}>
              <td>{j.job_name}</td>
              <td>
                <code>{j.cron}</code>
              </td>
              <td>{j.last_run_at ? formatTime(j.last_run_at) : strings.system.neverRun}</td>
              {testing && (
                <td>
                  <button
                    type="button"
                    disabled={busyJob === j.job_name}
                    onClick={() => run(j.job_name)}
                  >
                    {busyJob === j.job_name ? strings.system.running : strings.system.runNow}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <small>{strings.system.manualRunNote}</small>
      </p>
    </section>
  );
}
