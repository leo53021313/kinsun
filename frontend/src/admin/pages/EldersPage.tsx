import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { type AdminElder, listElders } from "../api";
import { formatTime } from "../format";
import { strings } from "../strings";

export function EldersPage() {
  const [elders, setElders] = useState<AdminElder[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    listElders().then(setElders, () => setError(true));
  }, []);

  if (error) return <p className="error-banner">{strings.common.loadFailedRefresh}</p>;
  return (
    <section>
      <h2>{strings.elders.title}</h2>
      {elders.length === 0 && <p>{strings.elders.noElders}</p>}
      {elders.map((e) => (
        <div className="card feed-item" key={e.elder_id}>
          <Link to={`/elders/${e.elder_id}`}>
            <strong>{e.name}</strong>
          </Link>
          <span className="feed-time">
            {e.bound_channels ? strings.elders.boundChannels(e.bound_channels) : strings.elders.notBound}
          </span>
          <span className="feed-time">
            {e.last_active_at ? strings.elders.lastActive(formatTime(e.last_active_at)) : strings.elders.noConversation}
          </span>
        </div>
      ))}
    </section>
  );
}
