import { useCallback, useState } from "react";

import {
  getMeta,
  getRagStatus,
  listJobs,
  runJob,
} from "../api";
import { formatTime } from "../format";
import { strings } from "../strings";
import { useLoadable } from "../useLoadable";

/** 系統頁（spec 2026-07-12 §3.3–3.4）：排程任務狀態；內測模式可立即執行。 */
export function SystemPage() {
  // 本頁不依賴路由參數，fetcher 永不回 null（其餘頁面以 null 表示「elderId 還沒
  // 解析出來、這輪不載入」）。
  const {
    data,
    error,
    reload: load,
  } = useLoadable(
    useCallback(async () => {
      const [jobsResult, rag, meta] = await Promise.all([listJobs(), getRagStatus(), getMeta()]);
      return {
        jobs: jobsResult.jobs,
        jobWarnings: jobsResult.meta.warnings,
        rag,
        testing: meta.internal_testing,
      };
    }, []),
  );
  const [notice, setNotice] = useState("");
  const [busyJob, setBusyJob] = useState("");

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
  if (!data) return <p>{strings.common.loading}</p>;
  const { jobs, jobWarnings, rag, testing } = data;
  return (
    <section>
      <h2>{strings.system.title}</h2>
      {notice && <p className="card">{notice}</p>}
      {/* 排程告警置頂：2026-07-26 排程停擺 13 天，這一頁當時只印了「上次執行」的
          時間戳——資料就在畫面上，卻沒有任何東西說它不對勁。 */}
      {jobWarnings.map((warning) => (
        <p className="error-banner" key={warning}>
          {warning}
        </p>
      ))}
      <div className="card">
        <h3>{strings.system.rag.heading}</h3>
        {rag.warnings.map((warning) => (
          <p className="error-banner" key={warning}>
            {warning}
          </p>
        ))}
        <p>
          {strings.system.rag.active}：{rag.active_release ?? strings.system.rag.none}
          {rag.active_published_at ? `（${formatTime(rag.active_published_at)}）` : ""}
        </p>
        <p>
          {strings.system.rag.latest}：{rag.latest_release ?? strings.system.rag.none}／
          {rag.latest_status ?? strings.system.rag.none}
        </p>
        <p>
          {strings.system.rag.counts(rag.document_count, rag.chunk_count)}　
          {strings.system.rag.policy}：{rag.content_policy}
        </p>
      </div>
      <table className="jobs-table">
        <thead>
          <tr>
            <th>{strings.system.columns.job}</th>
            <th>{strings.system.columns.cron}</th>
            <th>{strings.system.columns.lastRun}</th>
            <th>{strings.system.columns.health}</th>
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
              <td className={j.is_overdue || j.never_ran ? "job-unhealthy" : undefined}>
                {j.never_ran
                  ? strings.system.healthNeverRan
                  : j.is_overdue
                    ? strings.system.healthOverdue(j.late_seconds)
                    : strings.system.healthOk}
              </td>
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
