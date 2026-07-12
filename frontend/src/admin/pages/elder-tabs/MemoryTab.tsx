import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { type AdminElderMemory, getElderMemory } from "../../api";

/** 記憶與摘要分頁：AI 幫長輩記住的事（Mem0）＋每日對話摘要。 */
export function MemoryTab() {
  const { elderId } = useParams<{ elderId: string }>();
  const [data, setData] = useState<AdminElderMemory | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    getElderMemory(elderId).then(setData, () => setError(true));
  }, [elderId]);

  useEffect(load, [load]);

  if (error) return <p className="error-banner">載入失敗，請重新整理。</p>;
  if (!data) return <p>載入中…</p>;
  return (
    <div>
      <h3>長期記憶（AI 記住的事）</h3>
      {data.memories.length === 0 && <p>還沒有長期記憶。</p>}
      {data.memories.map((m, i) => (
        <div className="card" key={`${m.date}-${i}`}>
          {m.text}
          <small className="timeline-time">
            　{m.date}
            {m.provenance && `｜${m.provenance}`}
          </small>
        </div>
      ))}
      <h3>每日對話摘要</h3>
      {data.summaries.length === 0 && <p>還沒有摘要。</p>}
      {data.summaries.map((s) => (
        <div className="card" key={s.date}>
          <strong>{s.date}</strong>　{s.content}
        </div>
      ))}
    </div>
  );
}
