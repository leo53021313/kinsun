import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { type TraceDetail, getTrace } from "../api";
import { formatLatency, formatTime } from "../format";

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge ${status === "ok" ? "badge-ok" : "badge-error"}`}>
      {status === "ok" ? "成功" : "失敗"}
    </span>
  );
}

export function TraceDetailPage() {
  const { traceId } = useParams<{ traceId: string }>();
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!traceId) return;
    setError(null);
    getTrace(traceId).then(setTrace, (e) =>
      setError(e?.status === 404 ? "找不到這一輪的鏈路資料。" : "載入失敗，請重新整理。"),
    );
  }, [traceId]);

  useEffect(load, [load]);

  if (error) return <p className="error-banner">{error}</p>;
  if (!trace) return <p>載入中…</p>;
  return (
    <section>
      <h2>
        單輪處理鏈路　<small>{trace.elder_name || trace.line_user_id}</small>
      </h2>
      <button type="button" onClick={load}>
        重新整理
      </button>

      <div className={`trace-step${trace.webhook_event ? "" : " error"}`}>
        <h3>1. Webhook 收到</h3>
        {trace.webhook_event ? (
          <>
            <p>
              {formatTime(trace.webhook_event.created_at)}　類型：
              {trace.webhook_event.event_type}／{trace.webhook_event.message_type}
            </p>
            <details>
              <summary>原始 payload</summary>
              <pre>{JSON.stringify(trace.webhook_event.payload, null, 2)}</pre>
            </details>
          </>
        ) : (
          <p>沒有紀錄。</p>
        )}
      </div>

      <div className={`trace-step${trace.asr_call?.status === "error" ? " error" : ""}`}>
        <h3>2. ASR 辨識</h3>
        {trace.asr_call ? (
          <>
            <p>
              <StatusBadge status={trace.asr_call.status} />　
              {formatLatency(trace.asr_call.latency_ms)}
            </p>
            {trace.asr_call.transcript && <p>辨識結果：{trace.asr_call.transcript}</p>}
            {trace.asr_call.source_audio_url && (
              <audio controls src={trace.asr_call.source_audio_url} preload="none" />
            )}
            {trace.asr_call.error_message && (
              <p className="error-banner">{trace.asr_call.error_message}</p>
            )}
          </>
        ) : (
          <p>沒有紀錄。</p>
        )}
      </div>

      <div
        className={`trace-step${trace.llm_calls.some((c) => c.status === "error") ? " error" : ""}`}
      >
        <h3>3. LLM 生成</h3>
        {trace.llm_calls.length === 0 && <p>沒有紀錄。</p>}
        {trace.llm_calls.map((c, i) => (
          <div key={`${c.created_at}-${i}`}>
            <p>
              <StatusBadge status={c.status} />　{c.model_name}　{formatLatency(c.latency_ms)}
              {c.input_tokens !== null && `　token 入 ${c.input_tokens}／出 ${c.output_tokens}`}
            </p>
            {c.content && <p>回覆：{c.content}</p>}
            {c.error_message && <p className="error-banner">{c.error_message}</p>}
          </div>
        ))}
      </div>

      <div className={`trace-step${trace.tts_call?.status === "error" ? " error" : ""}`}>
        <h3>4. TTS 合成</h3>
        {trace.tts_call ? (
          <>
            <p>
              <StatusBadge status={trace.tts_call.status} />　
              {formatLatency(trace.tts_call.latency_ms)}
            </p>
            {trace.tts_call.error_message && (
              <p className="error-banner">{trace.tts_call.error_message}</p>
            )}
          </>
        ) : (
          <p>沒有紀錄。</p>
        )}
      </div>

      <div className="trace-step">
        <h3>5. 回覆送出</h3>
        {trace.reply ? (
          <>
            <p>
              <StatusBadge status={trace.reply.status} />　形式：
              {trace.reply.kind === "voice" ? "語音" : "文字"}　
              {formatLatency(trace.reply.latency_ms)}
            </p>
            {trace.reply.audio_url && (
              <audio controls src={trace.reply.audio_url} preload="none" />
            )}
          </>
        ) : (
          <p>沒有紀錄。</p>
        )}
      </div>

      {trace.risk_events.length > 0 && (
        <div className="trace-step error">
          <h3>風險事件</h3>
          {trace.risk_events.map((r, i) => (
            <p key={`${r.created_at}-${i}`}>
              <span className="badge badge-risk">L{r.tier}</span>　{r.reason}　
              {formatTime(r.created_at)}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
