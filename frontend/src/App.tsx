import liff from "@line/liff";
import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppointmentsPage } from "./pages/AppointmentsPage";
import { EldersPage } from "./pages/EldersPage";
import { MedicationsPage } from "./pages/MedicationsPage";

export function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        await liff.init({ liffId: import.meta.env.VITE_LIFF_ID });
        if (!liff.isLoggedIn()) {
          liff.login();
          return;
        }
        setReady(true);
      } catch {
        setError("初始化失敗，請稍後再試");
      }
    })();
  }, []);

  if (error) return <p>{error}</p>;
  if (!ready) return <p>載入中…</p>;
  return (
    <BrowserRouter basename="/liff">
      <Routes>
        <Route path="/" element={<EldersPage />} />
        <Route path="/elders/:elderId/medications" element={<MedicationsPage />} />
        <Route path="/elders/:elderId/appointments" element={<AppointmentsPage />} />
      </Routes>
    </BrowserRouter>
  );
}
