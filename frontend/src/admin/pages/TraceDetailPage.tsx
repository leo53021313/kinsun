import { useCallback } from "react";
import { useParams } from "react-router-dom";

import { getTrace } from "../api";
import { formatLatency, formatTime } from "../format";
import { strings } from "../strings";
import { useLoadable } from "../useLoadable";
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
  const {
    data: trace,
    error,
    reload: load,
  } = useLoadable(
    useCallback(() => (traceId ? getTrace(traceId) : null), [traceId]),
    // 錯誤型別由呼叫端決定：本頁要區分 404「查無此筆」與一般失敗，故為字串
    // 而非其餘六頁的布林。
    (e: unknown) =>
      (e as { status?: number })?.status === 404
        ? strings.trace.notFound
        : strings.common.loadFailedRefresh,
  );

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
      {/* 工程觀測開啟且捕捉到 Opik trace id 時才有網址；否則後端回空字串，這裡不渲染。 */}
      {trace.opik_url && (
        <a className="opik-link" href={trace.opik_url} target="_blank" rel="noreferrer">
          {strings.trace.openInOpik}
        </a>
      )}

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
        className={`trace-step${
          trace.rag_calls.some((call) => call.status === "error" || call.status === "urgent")
            ? " error"
            : ""
        }`}
      >
        <h3>{strings.trace.steps.rag}</h3>
        {trace.rag_calls.length === 0 && <p>{strings.trace.noRecord}</p>}
        {trace.rag_calls.map((call, index) => (
          <div key={`${call.created_at}-${index}`}>
            <p>
              <StatusBadge status={call.status === "normal" ? "ok" : call.status} />　
              {formatLatency(call.latency_ms)}　{strings.trace.ragRelease}
              {call.index_version || "—"}
            </p>
            <p>
              {strings.trace.ragQuery}
              {call.query}
            </p>
            <p>
              {strings.trace.ragReason}
              {call.reason}
            </p>
            {call.hits.length > 0 && (
              <details>
                <summary>{strings.trace.ragHits}</summary>
                <ul>
                  {call.hits.map((hit) => (
                    <li key={hit.chunk_id}>
                      {hit.source_id}／{hit.chunk_id}／{hit.retrieval_method}／
                      {hit.score.toFixed(3)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {call.citations.length > 0 && (
              <details>
                <summary>{strings.trace.ragCitations}</summary>
                <ul>
                  {call.citations.map((citation) => (
                    <li key={citation.chunk_id}>
                      <a href={citation.url} target="_blank" rel="noreferrer">
                        {citation.title}｜{citation.publisher}
                      </a>
                      <br />
                      <code>{citation.chunk_id}</code>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
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
