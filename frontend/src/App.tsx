import liff from "@line/liff";
import { useEffect, useState } from "react";

type Elder = { elder_id: string; name: string };
type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; elders: Elder[] };

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    void (async () => {
      try {
        await liff.init({ liffId: import.meta.env.VITE_LIFF_ID });
        if (!liff.isLoggedIn()) {
          liff.login();
          return;
        }
        const token = liff.getIDToken();
        if (!token) {
          setState({ kind: "error", message: "請重新登入" });
          return;
        }
        const res = await fetch("/api/me/elders", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 401) {
          setState({ kind: "error", message: "請重新登入" });
          return;
        }
        if (!res.ok) {
          setState({ kind: "error", message: "載入失敗，請稍後再試" });
          return;
        }
        const data = (await res.json()) as { elders: Elder[] };
        setState({ kind: "ready", elders: data.elders });
      } catch {
        setState({ kind: "error", message: "載入失敗，請稍後再試" });
      }
    })();
  }, []);

  if (state.kind === "loading") return <p>載入中…</p>;
  if (state.kind === "error") return <p>{state.message}</p>;
  if (state.elders.length === 0) {
    return <p>您還沒有長輩檔案。請在 LINE 回覆「設定」建立。</p>;
  }
  return (
    <main>
      <h1>您管理的長輩</h1>
      <ul>
        {state.elders.map((e) => (
          <li key={e.elder_id}>{e.name}</li>
        ))}
      </ul>
    </main>
  );
}
