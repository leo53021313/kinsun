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
  /**
   * ⚠️ 收 `Omit<Session, "role">`：**角色由工廠決定，呼叫端傳不進來**。
   *
   * 以前這裡收整個 `Session`，於是寫入那一路用的是呼叫端傳的 `next.role`，讀取
   * 與清除用的卻是工廠的 `role`。在長輩 context 上傳成 `guardian`，畫面顯示長輩
   * 已登入、token 卻落在家屬鍵、長輩鍵是 null；重整之後家屬欄變成登入、長輩欄
   * 空白——那是「兩欄互不干擾」唯一可被違反的路徑，而且看起來像永久故障。
   * 把 role 從簽章拿掉，讓它連傳錯都不可能。
   */
  signIn: (session: Omit<Session, "role">) => void;
  signOut: () => void;
};

export function createSessionContext(role: Role) {
  const Context = createContext<SessionContextValue | null>(null);

  function Provider(props: { children: ReactNode }) {
    // 用 lazy initializer 讀取：放在 effect 裡的話，第一次繪製會閃過一次
    // 「未登入」，兩欄同時閃很難看。
    const [session, setSession] = useState<Session | null>(() => loadSession(role));

    const signIn = useCallback((next: Omit<Session, "role">) => {
      // role 放在展開之後：呼叫端就算繞過型別硬塞一個角色進來，也蓋不掉這個
      // context 自己的角色。寫成 `{ role, ...next }` 的話同一個 bug 會原地復活。
      const session: Session = { ...next, role };
      saveSession(session);
      setSession(session);
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
