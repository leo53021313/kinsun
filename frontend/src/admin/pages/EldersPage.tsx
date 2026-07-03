import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { type AdminElder, listElders } from "../api";
import { formatTime } from "../format";

export function EldersPage() {
  const [elders, setElders] = useState<AdminElder[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    listElders().then(setElders, () => setError(true));
  }, []);

  if (error) return <p className="error-banner">載入失敗，請重新整理。</p>;
  return (
    <section>
      <h2>長輩清單</h2>
      {elders.length === 0 && <p>目前沒有長輩資料。</p>}
      {elders.map((e) => (
        <div className="card feed-item" key={e.elder_id}>
          <Link to={`/elders/${e.elder_id}`}>
            <strong>{e.name}</strong>
          </Link>
          <span className="feed-time">
            {e.line_user_id ? `LINE：${e.line_user_id}` : "尚未綁定 LINE"}
          </span>
          <span className="feed-time">
            {e.last_active_at ? `最後活動 ${formatTime(e.last_active_at)}` : "尚無對話"}
          </span>
        </div>
      ))}
    </section>
  );
}
