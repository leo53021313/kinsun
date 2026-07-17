import { useCallback } from "react";
import { useParams } from "react-router-dom";

import { getElderMemory } from "../../api";
import { strings } from "../../strings";
import { useLoadable } from "../../useLoadable";

/** 記憶與摘要分頁：AI 幫長輩記住的事（Mem0）＋每日對話摘要。 */
export function MemoryTab() {
  const { elderId } = useParams<{ elderId: string }>();
  const { data, error } = useLoadable(
    useCallback(() => (elderId ? getElderMemory(elderId) : null), [elderId]),
  );

  if (error) return <p className="error-banner">{strings.common.loadFailedRefresh}</p>;
  if (!data) return <p>{strings.common.loading}</p>;
  const memory = strings.elderTabs.memory;
  return (
    <div>
      <h3>{memory.longTermHeading}</h3>
      {data.memories.length === 0 && <p>{memory.noMemories}</p>}
      {data.memories.map((m, i) => (
        <div className="card" key={`${m.date}-${i}`}>
          {m.text}
          <small className="timeline-time">
            　{m.date}
            {m.provenance && `｜${m.provenance}`}
          </small>
        </div>
      ))}
      <h3>{memory.dailySummaryHeading}</h3>
      {data.summaries.length === 0 && <p>{memory.noSummaries}</p>}
      {data.summaries.map((s) => (
        <div className="card" key={s.date}>
          <strong>{s.date}</strong>　{s.content}
        </div>
      ))}
    </div>
  );
}
