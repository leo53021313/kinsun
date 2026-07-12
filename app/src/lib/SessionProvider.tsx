/**
 * 登入狀態集中管理（✅ D-45，丁-1）：Context 統一持有 session，
 * 各頁不再自行 loadSession()。持久化走 expo-secure-store（lib/auth，雙 slot）。
 * 內測（spec 2026-07-12）：另持有另一身分的 otherSession 與 internalTesting 旗標，
 * 供 RoleSwitcher 一鍵切換；正式使用下 otherSession 恆為 null、切換器不顯示。
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

import { ApiError, getMeta } from "@/lib/api";
import {
  clearSession,
  loadActiveSession,
  loadSessionForRole,
  saveSession,
  setActiveRole,
  type Role,
  type Session,
} from "@/lib/auth";

function otherRoleOf(role: Role): Role {
  return role === "guardian" ? "elder" : "guardian";
}

type SessionContextValue = {
  /** 首次載入 SecureStore 前為 true；期間請顯示載入畫面、勿導頁。 */
  loading: boolean;
  session: Session | null;
  /** 另一身分已存的登入（內測切換器用）。 */
  otherSession: Session | null;
  /** 內測模式（GET /api/v1/meta 下發；取不到一律視為 false）。 */
  internalTesting: boolean;
  signIn: (session: Session) => Promise<void>;
  /** 只登出目前身分；另一身分 slot 保留。 */
  signOut: () => Promise<void>;
  /** 切到另一身分（該身分需已有登入；無登入時為 no-op）。 */
  switchTo: (role: Role) => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider(props: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<Session | null>(null);
  const [otherSession, setOtherSession] = useState<Session | null>(null);
  const [internalTesting, setInternalTesting] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      const stored = await loadActiveSession();
      const other = stored ? await loadSessionForRole(otherRoleOf(stored.role)) : null;
      if (alive) {
        setSession(stored);
        setOtherSession(other);
        setLoading(false);
      }
    })();
    getMeta()
      .then((meta) => {
        if (alive) {
          setInternalTesting(meta.internal_testing);
        }
      })
      .catch(() => undefined); // 取不到＝正式行為：內測功能一律不顯示
    return () => {
      alive = false;
    };
  }, []);

  const signIn = useCallback(async (next: Session) => {
    await saveSession(next);
    setSession(next);
    setOtherSession(await loadSessionForRole(otherRoleOf(next.role)));
  }, []);

  const signOut = useCallback(async () => {
    if (session) {
      await clearSession(session.role);
    }
    setSession(null);
    setOtherSession(null);
  }, [session]);

  const switchTo = useCallback(async (role: Role) => {
    const target = await loadSessionForRole(role);
    if (!target) {
      return;
    }
    await setActiveRole(role);
    setSession(target);
    setOtherSession(await loadSessionForRole(otherRoleOf(role)));
  }, []);

  const value = useMemo(
    () => ({ loading, session, otherSession, internalTesting, signIn, signOut, switchTo }),
    [loading, session, otherSession, internalTesting, signIn, signOut, switchTo],
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

/** 401 統一處理（✅ 庚-28／F-11）：token 被撤銷（如「登出所有裝置」）時自動清
 * session——畫面既有的 session 守衛隨即導回登入，不再永遠「載入失敗」。
 * 回傳 true＝已處理，呼叫端直接 return、不再顯示錯誤文字。
 * 登入／註冊頁勿用（該處 401＝帳密錯誤，要顯示訊息）。 */
export function useSignOutOnAuthError(): (exc: unknown) => Promise<boolean> {
  const { signOut } = useSession();
  return useCallback(
    async (exc: unknown) => {
      if (exc instanceof ApiError && exc.status === 401) {
        await signOut();
        return true;
      }
      return false;
    },
    [signOut],
  );
}
