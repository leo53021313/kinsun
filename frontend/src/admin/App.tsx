import { useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";

import { getAdminKey, setAdminKey } from "./api";
import { MessagesPage } from "./pages/MessagesPage";
import { OverviewPage } from "./pages/OverviewPage";

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

function Placeholder({ title }: { title: string }) {
  return <p>{title}（建置中）</p>;
}

export function App() {
  const [hasKey, setHasKey] = useState(() => getAdminKey() !== null);
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
          <Route path="/elders" element={<Placeholder title="長輩清單" />} />
          <Route path="/elders/:elderId" element={<Placeholder title="長輩時間軸" />} />
          <Route path="/traces/:traceId" element={<Placeholder title="單輪鏈路" />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
