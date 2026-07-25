import { useEffect, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router";

import { getAdminKey, setAdminKey, setOnUnauthorized } from "./api";
import { strings } from "./strings";
import { ElderDetailPage } from "./pages/ElderDetailPage";
import { EldersPage } from "./pages/EldersPage";
import { MessagesPage } from "./pages/MessagesPage";
import { NewsPage } from "./pages/NewsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SystemPage } from "./pages/SystemPage";
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
      <h1>{strings.app.title}</h1>
      <input
        type="password"
        placeholder={strings.app.keyPlaceholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit">{strings.app.enter}</button>
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
        <strong>{strings.app.title}</strong>
        <NavLink to="/" end>
          {strings.app.nav.overview}
        </NavLink>
        <NavLink to="/messages">{strings.app.nav.messages}</NavLink>
        <NavLink to="/elders">{strings.app.nav.elders}</NavLink>
        <NavLink to="/news">{strings.app.nav.news}</NavLink>
        <NavLink to="/system">{strings.app.nav.system}</NavLink>
      </nav>
      <main className="admin-main">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/messages" element={<MessagesPage />} />
          <Route path="/elders" element={<EldersPage />} />
          <Route path="/elders/:elderId" element={<ElderDetailPage />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/system" element={<SystemPage />} />
          <Route path="/traces/:traceId" element={<TraceDetailPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
