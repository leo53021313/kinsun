import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { type TraceDetail, getTrace } from "../api";
import { formatLatency, formatTime } from "../format";
import { strings } from "../strings";
import { adminTierLabel } from "kinsun-shared/terms";

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge ${status === "ok" ? "badge-ok" : "badge-error"}`}>
      {status === "ok" ? strings.trace.statusOk : strings.trace.statusFail}
    </span>
  );
}

export function TraceDetailPage() {
  const { traceId } = useParams<{ traceId: string }>();
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!traceId) return;
    // setError(null) 放進成功處理器：開頭的同步 setState 會在 useEffect 中
    // 觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    getTrace(traceId).then(
      (trace) => {
        setTrace(trace);
        setError(null);
      },
      (e) =>
        setError(e?.status === 404 ? strings.trace.notFound : strings.common.loadFailedRefresh),
    );
  }, [traceId]);

  useEffect(load, [load]);

  if (error) return <p className="error-banner">{error}</p>;
  if (!trace) return <p>{strings.common.loading}</p>;
  return (
    <section>
      <h2>
        {strings.trace.title}　<small>{trace.elder_name || trace.external_id}</small>
      </h2>
      <button type="button" onClick={load}>
        {strings.common.refresh}
      </button>

      <div className={`trace-step${trace.webhook_event ? "" : " error"}`}>
        <h3>{strings.trace.steps.webhook}</h3>
        {trace.webhook_event ? (
          <>
            <p>
              {formatTime(trace.webhook_event.created_at)}　{strings.trace.typeLabel}
              {trace.webhook_event.event_type}／{trace.webhook_event.message_type}
            </p>
            <details>
              <summary>{strings.trace.rawPayload}</summary>
              <pre>{JSON.stringify(trace.webhook_event.payload, null, 2)}</pre>
            </details>
          </>
        ) : (
          <p>{strings.trace.noRecord}</p>
        )}
      </div>

      <div className={`trace-step${trace.asr_call?.status === "error" ? " error" : ""}`}>
        <h3>{strings.trace.steps.asr}</h3>
        {trace.asr_call ? (
          <>
            <p>
              <StatusBadge status={trace.asr_call.status} />　
              {formatLatency(trace.asr_call.latency_ms)}
            </p>
            {trace.asr_call.transcript && (
              <p>
                {strings.trace.asrTranscript}
                {trace.asr_call.transcript}
              </p>
            )}
            {trace.asr_call.source_audio_url && (
              <audio controls src={trace.asr_call.source_audio_url} preload="none" />
            )}
            {trace.asr_call.error_message && (
              <p className="error-banner">{trace.asr_call.error_message}</p>
            )}
          </>
        ) : (
          <p>{strings.trace.noRecord}</p>
        )}
      </div>

      <div
        className={`trace-step${trace.llm_calls.some((c) => c.status === "error") ? " error" : ""}`}
      >
        <h3>{strings.trace.steps.llm}</h3>
        {trace.llm_calls.length === 0 && <p>{strings.trace.noRecord}</p>}
        {trace.llm_calls.map((c, i) => (
          <div key={`${c.created_at}-${i}`}>
            <p>
              <StatusBadge status={c.status} />　{c.model_name}　{formatLatency(c.latency_ms)}
              {c.input_tokens !== null && strings.trace.llmTokens(c.input_tokens, c.output_tokens)}
            </p>
            {c.content && (
              <p>
                {strings.trace.llmReply}
                {c.content}
              </p>
            )}
            {c.error_message && <p className="error-banner">{c.error_message}</p>}
          </div>
        ))}
      </div>

      <div className={`trace-step${trace.tts_call?.status === "error" ? " error" : ""}`}>
        <h3>{strings.trace.steps.tts}</h3>
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
          <p>{strings.trace.noRecord}</p>
        )}
      </div>

      <div className="trace-step">
        <h3>{strings.trace.steps.reply}</h3>
        {trace.reply ? (
          <>
            <p>
              <StatusBadge status={trace.reply.status} />　{strings.trace.replyKindLabel}
              {trace.reply.kind === "voice" ? strings.trace.replyVoice : strings.trace.replyText}　
              {formatLatency(trace.reply.latency_ms)}
            </p>
            {trace.reply.audio_url && (
              <audio controls src={trace.reply.audio_url} preload="none" />
            )}
          </>
        ) : (
          <p>{strings.trace.noRecord}</p>
        )}
      </div>

      {trace.risk_events.length > 0 && (
        <div className="trace-step error">
          <h3>{strings.trace.steps.risk}</h3>
          {trace.risk_events.map((r, i) => (
            <p key={`${r.created_at}-${i}`}>
              <span className="badge badge-risk">{adminTierLabel(r.tier)}</span>　{r.reason}　
              {formatTime(r.created_at)}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
