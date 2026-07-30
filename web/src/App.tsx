/**
 * 路由與階段。
 *
 * ⚠️ 只有兩條路由：開場與舞台。手機外框**內部**的畫面切換是元件狀態，不進
 * 網址列——兩欄同時存在，讓它們去搶同一條網址只會互相覆蓋。
 *
 * ⚠️ 撕裂動畫期間舞台就已經掛載並開始請求（TearTransition 疊在它上面）。
 * 等動畫播完才開始載，使用者會平白多等 700 毫秒。
 */

import { useCallback, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router";

import { GatePage } from "./gate/GatePage";
import { StagePage } from "./stage/StagePage";
import { TearTransition } from "./stage/TearTransition";

function Gate() {
  const navigate = useNavigate();
  const [tearing, setTearing] = useState(false);
  const done = useCallback(() => navigate("/stage", { replace: true }), [navigate]);

  return (
    <>
      {/* 舞台先掛上去，撕裂的那兩半疊在它上面滑開，後方就已經載好了。 */}
      {tearing ? <StagePage /> : null}
      <TearTransition active={tearing} onDone={done}>
        <GatePage onStart={() => setTearing(true)} />
      </TearTransition>
    </>
  );
}

export function App() {
  return (
    <BrowserRouter basename="/demo">
      <Routes>
        <Route path="/" element={<Gate />} />
        <Route path="/stage" element={<StagePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
