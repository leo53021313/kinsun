/**
 * 登入狀態集中管理（✅ D-45，丁-1）：Context 統一持有 session，
 * 各頁不再自行 loadSession()。持久化仍走 expo-secure-store（lib/auth）。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { clearSession, loadSession, saveSession, type Session } from "@/lib/auth";

type SessionContextValue = {
  /** 首次載入 SecureStore 前為 true；期間請顯示載入畫面、勿導頁。 */
  loading: boolean;
  session: Session | null;
  signIn: (session: Session) => Promise<void>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider(props: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    let alive = true;
    loadSession().then((stored) => {
      if (alive) {
        setSession(stored);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  const signIn = useCallback(async (next: Session) => {
    await saveSession(next);
    setSession(next);
  }, []);

  const signOut = useCallback(async () => {
    await clearSession();
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({ loading, session, signIn, signOut }),
    [loading, session, signIn, signOut],
  );
  return <SessionContext.Provider value={value}>{props.children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error("useSession 必須在 SessionProvider 之內使用（見 app/_layout.tsx）");
  }
  return value;
}
