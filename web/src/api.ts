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
