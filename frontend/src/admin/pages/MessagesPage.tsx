import { useRef, useState } from "react";
import { Link } from "react-router";

import { type FeedMessage, listMessages, listMessagesBefore } from "../api";
import { formatTime } from "../format";
import { strings } from "../strings";
import { usePolling } from "../usePolling";
import { adminTierLabel } from "kinsun-shared/terms";

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
      <h2>{strings.messages.title}</h2>
      {disconnected && <p className="error-banner">{strings.common.disconnected}</p>}
      {messages.length === 0 && !disconnected && <p>{strings.messages.noMessages}</p>}
      {messages.map((m) => (
        <div className="card feed-item" key={messageKey(m)}>
          <span className="feed-time">{formatTime(m.created_at)}</span>
          <span className={`badge badge-${m.kind}`}>
            {strings.messages.kindLabel[m.kind] ?? m.kind}
          </span>
          <span>
            <strong>{m.elder_name || m.elder_id}</strong>
            {m.role && (
              <em>（{m.role === "user" ? strings.common.roleElder : strings.common.roleAssistant}）</em>
            )}
            ：{m.content}
            {m.tier !== null && (
              <span>
                {" "}
                {strings.messages.tierPrefix} {adminTierLabel(m.tier)}
              </span>
            )}
            {m.trace_id && <Link to={`/traces/${m.trace_id}`}>　{strings.common.viewTrace}</Link>}
          </span>
        </div>
      ))}
      {messages.length > 0 && hasOlder && (
        <button type="button" className="load-older" onClick={loadOlder} disabled={loadingOlder}>
          {loadingOlder ? strings.common.loading : strings.messages.loadOlder}
        </button>
      )}
    </section>
  );
}
