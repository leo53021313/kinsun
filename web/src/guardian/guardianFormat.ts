/**
 * 家屬端 W6 兩支畫面的純格式化函式。
 *
 * ⚠️ 與畫面分成不同檔案，理由同 `guardianTabsContext.ts`：一個檔案若同時匯出元件與
 * 非元件，Fast Refresh 會整檔重載而不是熱替換（eslint 的
 * `react-refresh/only-export-components`）。兩者都是純函式、沒有 React 相依，獨立
 * 測試也比透過畫面測直接。
 */

import type { DailySummary } from "kinsun-shared/types";

/** 分享給家人的文字。末尾標明來源是服務（金孫），不是角色。 */
export function buildShareText(summary: DailySummary): string {
  return `${summary.date} 的摘要\n\n${summary.content}\n\n（由金孫產生）`;
}

/**
 * epoch 秒 → 表單看得懂的「YYYY-MM-DD HH:mm」。
 *
 * 整點零分時只留日期：後端對「只知道哪一天、還沒約時間」的回診就是存 00:00，
 * 把它顯示成「00:00」會讓家屬以為醫院約在半夜。
 */
export function formatAppointmentWhen(eventAt: number | null): string {
  if (eventAt === null) return "";
  const value = new Date(eventAt * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
  if (value.getHours() === 0 && value.getMinutes() === 0) return date;
  return `${date} ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}
