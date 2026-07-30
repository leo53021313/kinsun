/**
 * 雙角色 session 的 Context 工廠。
 *
 * ⚠️ **為什麼是工廠而不是單例**：App 的 SessionProvider 掛在根節點，一個分頁
 * 只有一份登入狀態。這裡左右兩欄要同時各自登入，那個形狀行不通。每次呼叫產生
 * 一組獨立的 Provider 與 hook，儲存鍵也分開——這是本前端與 App 最根本的差異。
 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { clearSession, loadSession, saveSession, type Role, type Session } from "./storage";

type SessionContextValue = {
  session: Session | null;
  signIn: (session: Session) => void;
  signOut: () => void;
};

export function createSessionContext(role: Role) {
  const Context = createContext<SessionContextValue | null>(null);

  function Provider(props: { children: ReactNode }) {
    // 用 lazy initializer 讀取：放在 effect 裡的話，第一次繪製會閃過一次
    // 「未登入」，兩欄同時閃很難看。
    const [session, setSession] = useState<Session | null>(() => loadSession(role));

    const signIn = useCallback((next: Session) => {
      saveSession(next);
      setSession(next);
    }, []);

    const signOut = useCallback(() => {
      clearSession(role);
      setSession(null);
    }, []);

    const value = useMemo(() => ({ session, signIn, signOut }), [session, signIn, signOut]);
    return <Context.Provider value={value}>{props.children}</Context.Provider>;
  }

  function useSession(): SessionContextValue {
    const value = useContext(Context);
    if (value === null) {
      throw new Error(`useSession（${role}）必須在對應的 Provider 之內使用`);
    }
    return value;
  }

  return { Provider, useSession };
}
