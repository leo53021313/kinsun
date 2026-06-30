import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { type Elder, listElders } from "../api";

export function EldersPage() {
  const [elders, setElders] = useState<Elder[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listElders()
      .then(setElders)
      .catch(() => setError("載入失敗，請稍後再試"));
  }, []);

  if (error) return <p>{error}</p>;
  if (!elders) return <p>載入中…</p>;
  if (elders.length === 0) return <p>您還沒有長輩檔案。請在 LINE 回覆「設定」建立。</p>;
  return (
    <main>
      <h1>您管理的長輩</h1>
      <ul>
        {elders.map((e) => (
          <li key={e.elder_id}>
            <Link to={`/elders/${e.elder_id}/medications`}>{e.name}</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
