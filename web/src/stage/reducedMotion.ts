/**
 * 使用者是否要求「減少動態效果」（`prefers-reduced-motion`，W-11）。
 *
 * ⚠️ 抽成獨立模組供 `stage/TearTransition.tsx` 與 `notify/NotificationBanner.tsx`
 * 共用（審查修正，2026-07-31）：兩者原本各自宣告一份一模一樣的判斷式，這與
 * `notify/osStyle.ts` 對 `PhoneOs` 型別「不重新宣告、只轉出」的理由完全相同
 * ——各自宣告一份的話，兩邊哪天分岔了，沒有任何機制會提醒。
 */
export function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}
