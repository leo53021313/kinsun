/**
 * 後端 API 呼叫端。共同流程（信封／204／錯誤）住共用包（✅ 庚-30），
 * 此處只注入本端的差異：**同源相對路徑**與 Bearer token。
 *
 * ⚠️ 刻意不設 baseUrl：靜態檔由後端掛在 /demo，與 API 同源。後端沒有 CORS
 * middleware，一旦改成打絕對位址，瀏覽器會直接擋下所有請求。
 *
 * 所有 JSON 欄位 snake_case，與後端完全同鍵名（AGENTS.md）。
 */

import { createApiClient } from "kinsun-shared/client";
import { ApiError } from "kinsun-shared/envelope";

export { ApiError };

const client = createApiClient({
  authHeaders: (token) => {
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  },
});

export const request = client.request;

/** 運營狀態（spec W-03）。分項的鍵與狀態值皆為後端定義的字面值，文案在 strings.ts。 */
export type DemoStatus = {
  overall: string;
  components: Record<string, string>;
};

export function getDemoStatus(): Promise<DemoStatus> {
  return request<DemoStatus>("/api/v1/demo-status");
}

/**
 * 取出 ApiError 給人看的訊息；非後端信封訊息一律退回 `fallback`。
 *
 * `shared/client.ts` 在後端回應不是合法 JSON 時（Cloudflare 隧道抖動回的 502
 * HTML、或後端未捕捉例外走 Starlette 預設處理的 text/plain 500），會自造一個
 * `http_<status>` 開頭的 code，訊息內容是英文字面值（如 `HTTP 502`），不是給人看
 * 的話——直接顯示會讓使用者在畫面上看到「HTTP 502」。只有後端真的解出信封、
 * 帶著繁中 `message` 的 ApiError 才直接顯示；其餘（含這種自造錯誤、以及非
 * ApiError 的例外，如 fetch 自己擲的 TypeError）一律用呼叫端指定的繁中預設訊息。
 */
export function apiErrorMessage(exc: unknown, fallback: string): string {
  if (exc instanceof ApiError && !exc.code.startsWith("http_")) {
    return exc.message;
  }
  return fallback;
}
