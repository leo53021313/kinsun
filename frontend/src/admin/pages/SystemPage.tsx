import { useCallback, useEffect, useState } from "react";

import { type AdminJob, getMeta, listJobs, runJob } from "../api";
import { formatTime } from "../format";

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
      setNotice(`已執行 ${jobName}。`);
      load();
    } catch {
      setNotice("執行失敗，請確認內測模式是否開啟。");
    } finally {
      setBusyJob("");
    }
  }

  if (error) return <p className="error-banner">載入失敗，請重新整理。</p>;
  if (!jobs) return <p>載入中…</p>;
  return (
    <section>
      <h2>系統排程</h2>
      {notice && <p className="card">{notice}</p>}
      <table className="jobs-table">
        <thead>
          <tr>
            <th>任務</th>
            <th>排程（cron）</th>
            <th>上次執行</th>
            {testing && <th>操作</th>}
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.job_name}>
              <td>{j.job_name}</td>
              <td>
                <code>{j.cron}</code>
              </td>
              <td>{j.last_run_at ? formatTime(j.last_run_at) : "尚未執行"}</td>
              {testing && (
                <td>
                  <button
                    type="button"
                    disabled={busyJob === j.job_name}
                    onClick={() => run(j.job_name)}
                  >
                    {busyJob === j.job_name ? "執行中…" : "立即執行（內測）"}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <small>手動執行不會更新「上次執行」（不干擾排程器的到期判斷）。</small>
      </p>
    </section>
  );
}
