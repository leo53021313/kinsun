/**
 * 401 統一處理（沿用 App 的 ✅ 庚-28／F-11）：token 被撤銷（例如在另一台裝置
 * 按了「登出所有裝置」）時自動清掉登入，畫面的守衛隨即導回登入頁。
 *
 * 回 true ＝已處理，呼叫端直接 return、不要再顯示錯誤文字。
 *
 * ⚠️ 登入／註冊畫面**不要用**：那裡的 401 是「帳號或密碼不對」，要顯示訊息給人看，
 * 不是把人踢出去。
 */

import { ApiError } from "@/api";

export function makeSignOutOnAuthError(signOut: () => void): (exc: unknown) => boolean {
  return (exc: unknown) => {
    if (exc instanceof ApiError && exc.status === 401) {
      signOut();
      return true;
    }
    return false;
  };
}
