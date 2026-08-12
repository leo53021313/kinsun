/**
 * 「目前這位長輩」的 context 與取用端。
 *
 * ⚠️ 與 `GuardianTabsProvider.tsx` 分成兩個檔案，理由同 `session/contexts.ts`：
 * 一個檔案若同時匯出元件與非元件，Fast Refresh 會整檔重載而不是熱替換
 * （eslint 的 `react-refresh/only-export-components` 擋的就是這個）。相依方向是
 * 單向的（Provider → 本檔），不會有循環匯入。
 */

import { createContext, useContext } from "react";

import type { Elder } from "kinsun-shared/types";

import { strings } from "@/strings";

export type PrimaryElderResult = { elder: Elder | null; error: string };

export type GuardianTabsState = {
  primaryElder: Elder | null;
  loaded: boolean;
  error: string;
  refreshPrimaryElder: () => Promise<PrimaryElderResult>;
};

export const GuardianTabsContext = createContext<GuardianTabsState | null>(null);

export function useGuardianTabsState(): GuardianTabsState {
  const value = useContext(GuardianTabsContext);
  if (value === null) {
    throw new Error("useGuardianTabsState 必須在 GuardianTabsProvider 之內使用");
  }
  return value;
}

/** 這一項 tab 要顯示的長輩稱呼；讀不到就退回設計稿的預設字樣。 */
export function primaryElderLabel(elder: Elder | null): string {
  return elder?.nickname?.trim() || elder?.name?.trim() || strings.guardianTabs.profileFallback;
}
