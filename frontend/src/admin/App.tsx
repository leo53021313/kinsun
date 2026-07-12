import { useEffect, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";

import { getAdminKey, setAdminKey, setOnUnauthorized } from "./api";
import { EldersPage } from "./pages/EldersPage";
import { ElderTimelinePage } from "./pages/ElderTimelinePage";
import { MessagesPage } from "./pages/MessagesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { TraceDetailPage } from "./pages/TraceDetailPage";

function KeyForm({ onSubmit }: { onSubmit: () => void }) {
  const [value, setValue] = useState("");
  return (
    <form
      className="key-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!value.trim()) return;
        setAdminKey(value.trim());
        onSubmit();
      }}
    >
      <h1>金孫 觀測後台</h1>
      <input
        type="password"
        placeholder="請輸入管理金鑰"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit">進入</button>
    </form>
  );
}

export function App() {
  const [hasKey, setHasKey] = useState(() => getAdminKey() !== null);
  // 金鑰失效自動回輸入頁（✅ D-52 丁-7）：任何 API 401 即切換。
  useEffect(() => {
    setOnUnauthorized(() => setHasKey(false));
    return () => setOnUnauthorized(null);
  }, []);
  if (!hasKey) return <KeyForm onSubmit={() => setHasKey(true)} />;
  return (
    <BrowserRouter basename="/admin">
      <nav className="admin-nav">
        <strong>金孫 觀測後台</strong>
        <NavLink to="/" end>
          總覽
        </NavLink>
        <NavLink to="/messages">訊息流</NavLink>
        <NavLink to="/elders">長輩</NavLink>
      </nav>
      <main className="admin-main">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/messages" element={<MessagesPage />} />
          <Route path="/elders" element={<EldersPage />} />
          <Route path="/elders/:elderId" element={<ElderTimelinePage />} />
          <Route path="/traces/:traceId" element={<TraceDetailPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
