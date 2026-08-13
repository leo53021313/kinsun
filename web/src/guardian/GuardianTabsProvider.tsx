/**
 * 家屬端「目前這位長輩」的集中出處（W5）。
 *
 * ## 暫用選取規則：後端清單第一位
 *
 * 正式產品支援多位長輩，但交付稿還沒定義切換器。把這條暫用規則集中在一個
 * Provider，之後補「目前選定長輩」時不必逐頁拆除寫死的 elder_id——這是 App 那側
 * （`app/src/lib/GuardianTabsProvider.tsx`）的作法，web 照搬同一個結構與理由。
 *
 * ⚠️ **W5a 只建立這個 Provider，還沒有人掛它。** 掛載點在 `GuardianApp`，與五項
 * Tabs 一起於 W5b 接上——那一批才會動到家屬端的導覽結構。這裡先獨立完成、獨立
 * 測試，是為了讓風險最高的那一批只需要處理導覽本身。
 *
 * ⚠️ `requestIdRef` 不可省：家屬連按兩次「再試一次」時，兩個請求會同時在路上，
 * 先發的若後回就會用舊結果蓋掉新結果。只認最後一次發出的請求。
 */

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Elder } from "kinsun-shared/types";

import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";

import { listElders } from "./api";
import { GuardianTabsContext, type PrimaryElderResult } from "./guardianTabsContext";

export function GuardianTabsProvider(props: { children: ReactNode }) {
  const { session, signOut } = GuardianSession.useSession();
  const [primaryElder, setPrimaryElder] = useState<Elder | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const requestIdRef = useRef(0);

  const signOutOn401 = useMemo(() => makeSignOutOnAuthError(signOut), [signOut]);

  const loadPrimaryElder = useCallback(async (): Promise<PrimaryElderResult> => {
    if (!session) {
      return { elder: null, error: "" };
    }
    try {
      const elder = (await listElders(session.token))[0] ?? null;
      return { elder, error: "" };
    } catch (exc) {
      // 401＝token 被撤銷，統一處理會把人踢回登入畫面；這裡不再顯示錯誤文字。
      if (signOutOn401(exc)) {
        return { elder: null, error: "" };
      }
      return {
        elder: null,
        error: exc instanceof Error ? exc.message : strings.common.loadFailed,
      };
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
      setError(result.error);
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
      setError(result.error);
    });
    return () => {
      isActive = false;
    };
  }, [loadPrimaryElder]);

  const value = useMemo(
    () => ({ primaryElder, loaded, error, refreshPrimaryElder }),
    [primaryElder, loaded, error, refreshPrimaryElder],
  );

  return (
    <GuardianTabsContext.Provider value={value}>{props.children}</GuardianTabsContext.Provider>
  );
}
