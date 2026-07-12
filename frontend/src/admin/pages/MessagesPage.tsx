import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { type FeedMessage, listMessages, listMessagesBefore } from "../api";
import { formatTime } from "../format";
import { usePolling } from "../usePolling";

const KIND_LABEL: Record<string, string> = {
  turn: "對話",
  reminder: "推播",
  risk: "風險",
};

function messageKey(m: FeedMessage): string {
  return `${m.kind}-${m.created_at}-${m.elder_id}-${m.content}`;
}

export function MessagesPage() {
  const [messages, setMessages] = useState<FeedMessage[]>([]);
  const [disconnected, setDisconnected] = useState(false);
  const [hasOlder, setHasOlder] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const lastSeen = useRef(0);

  // 回翻歷史（✅ D-29 乙-6）：以最舊一筆為游標往回撈。
  async function loadOlder() {
    const oldest = messages[messages.length - 1]?.created_at;
    if (!oldest || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const { messages: older, hasMore } = await listMessagesBefore(oldest);
      setHasOlder(hasMore);
      setMessages((prev) => {
        const seen = new Set(prev.map(messageKey));
        return [...prev, ...older.filter((m) => !seen.has(messageKey(m)))];
      });
    } catch {
      setDisconnected(true);
    } finally {
      setLoadingOlder(false);
    }
  }

  usePolling(async () => {
    try {
      const fresh = await listMessages(lastSeen.current);
      setDisconnected(false);
      if (fresh.length === 0) return;
      lastSeen.current = Math.max(lastSeen.current, ...fresh.map((m) => m.created_at));
      setMessages((prev) => {
        const seen = new Set(prev.map(messageKey));
        const added = fresh.filter((m) => !seen.has(messageKey(m)));
        return [...added, ...prev].slice(0, 500);
      });
    } catch {
      setDisconnected(true); // 保留既有資料，只顯示中斷提示
    }
  }, 5000);

  return (
    <section>
      <h2>全域訊息流</h2>
      {disconnected && <p className="error-banner">連線中斷，重試中…</p>}
      {messages.length === 0 && !disconnected && <p>目前沒有訊息。</p>}
      {messages.map((m) => (
        <div className="card feed-item" key={messageKey(m)}>
          <span className="feed-time">{formatTime(m.created_at)}</span>
          <span className={`badge badge-${m.kind}`}>{KIND_LABEL[m.kind] ?? m.kind}</span>
          <span>
            <strong>{m.elder_name || m.elder_id}</strong>
            {m.role && <em>（{m.role === "user" ? "長輩" : "金孫"}）</em>}
            ：{m.content}
            {m.tier !== null && <span> 等級 L{m.tier}</span>}
            {m.trace_id && <Link to={`/traces/${m.trace_id}`}>　檢視鏈路</Link>}
          </span>
        </div>
      ))}
      {messages.length > 0 && hasOlder && (
        <button type="button" className="load-older" onClick={loadOlder} disabled={loadingOlder}>
          {loadingOlder ? "載入中…" : "載入更早的訊息"}
        </button>
      )}
    </section>
  );
}
