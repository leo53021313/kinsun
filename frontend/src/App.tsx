import liff from "@line/liff";
import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { EldersPage } from "./pages/EldersPage";
import { SchedulesPage } from "./pages/SchedulesPage";
import { HealthReportPage } from "./pages/HealthReportPage";
import { strings } from "./strings";

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
        setError(strings.app.initFailed);
      }
    })();
  }, []);

  if (error) return <p>{error}</p>;
  if (!ready) return <p>{strings.common.loading}</p>;
  return (
    <BrowserRouter basename="/liff">
      <Routes>
        <Route path="/" element={<EldersPage />} />
        <Route path="/elders/:elderId/schedules" element={<SchedulesPage />} />
        <Route path="/elders/:elderId/health-report" element={<HealthReportPage />} />
      </Routes>
    </BrowserRouter>
  );
}
