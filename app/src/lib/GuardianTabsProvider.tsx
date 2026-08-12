import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { listElders, type Elder } from "@/lib/api";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";

type PrimaryElderResult = {
  elder: Elder | null;
  error: string | null;
};

type GuardianTabsState = {
  primaryElder: Elder | null;
  loaded: boolean;
  error: string;
  refreshPrimaryElder: () => Promise<PrimaryElderResult>;
};

const GuardianTabsContext = createContext<GuardianTabsState | null>(null);

/**
 * 批次 5 的暫用選取規則：以後端清單第一位作目前長輩。
 *
 * 正式 App 支援多位長輩，但交付稿尚未定義切換器；這個 Provider 把暫用規則集中在
 * 一處，之後補「目前選定長輩」時不必逐頁拆除寫死的 elder_id。
 */
export function GuardianTabsProvider(props: { children: ReactNode }) {
  const { session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const [primaryElder, setPrimaryElder] = useState<Elder | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const requestIdRef = useRef(0);

  const loadPrimaryElder = useCallback(async (): Promise<PrimaryElderResult> => {
    if (!session || session.role !== "guardian") {
      return { elder: null, error: null };
    }

    try {
      const elder = (await listElders(session.token))[0] ?? null;
      return { elder, error: null };
    } catch (exc) {
      if (await signOutOn401(exc)) {
        return { elder: null, error: null };
      }
      const message = exc instanceof Error ? exc.message : strings.common.loadFailedShort;
      return { elder: null, error: message };
    }
  }, [session, signOutOn401]);

  const refreshPrimaryElder = useCallback(async (): Promise<PrimaryElderResult> => {
    const requestId = ++requestIdRef.current;
    setLoaded(false);
    setError("");
    const result = await loadPrimaryElder();
    if (requestId === requestIdRef.current) {
      setPrimaryElder(result.elder);
      setLoaded(true);
      setError(result.error ?? "");
    }
    return result;
  }, [loadPrimaryElder]);

  useEffect(() => {
    let isActive = true;
    const requestId = ++requestIdRef.current;

    void loadPrimaryElder().then((result) => {
      if (!isActive || requestId !== requestIdRef.current) return;
      setPrimaryElder(result.elder);
      setLoaded(true);
      setError(result.error ?? "");
    });

    return () => {
      isActive = false;
    };
  }, [loadPrimaryElder]);

  const value = useMemo(
    () => ({ primaryElder, loaded, error, refreshPrimaryElder }),
    [primaryElder, loaded, error, refreshPrimaryElder],
  );

  return <GuardianTabsContext.Provider value={value}>{props.children}</GuardianTabsContext.Provider>;
}

export function useGuardianTabsState(): GuardianTabsState {
  const value = useContext(GuardianTabsContext);
  if (value === null) {
    throw new Error("useGuardianTabsState 必須在 GuardianTabsProvider 內使用");
  }
  return value;
}
