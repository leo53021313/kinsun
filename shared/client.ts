/**
 * 三端共用 HTTP client 工廠（✅ 庚-30／F-12）：發請求 → 204 → 解析 JSON →
 * 解包信封 → ApiError 的共同流程只寫一份；三端差異（App Bearer token、
 * LIFF ID token、admin X-Admin-Key）以設定注入。
 * 純 TS、零依賴（fetch／Headers 由各端執行環境提供：瀏覽器與 React Native 皆內建）。
 */

import { ApiError, type Envelope, unwrapEnvelope } from "./envelope";

export type RequestOptions = RequestInit & {
  /** 逐次請求的 Bearer token（App 端用；authHeaders 收到後自行組頭）。 */
  token?: string;
};

export type ApiClientConfig = {
  /** 絕對位址前綴（App 用）。未設定時可自行擲 ApiError；省略＝同源相對路徑。 */
  baseUrl?: () => string;
  /** 每次請求的認證頭；token 為呼叫端逐次傳入。 */
  authHeaders?: (token?: string) => Record<string, string>;
  /** 收到 401 時先行通知（admin 金鑰失效切回輸入頁用），照常繼續解包擲錯。 */
  onUnauthorized?: () => void;
};

export function createApiClient(config: ApiClientConfig = {}) {
  async function requestWithMeta<T>(
    path: string,
    init: RequestOptions = {},
  ): Promise<{ data: T; meta: Record<string, unknown> | null }> {
    const prefix = config.baseUrl ? config.baseUrl() : "";
    const { token, ...rest } = init;
    const headers = new Headers(rest.headers);
    if (rest.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    for (const [key, value] of Object.entries(config.authHeaders?.(token) ?? {})) {
      headers.set(key, value);
    }
    const res = await fetch(`${prefix}${path}`, { ...rest, headers });
    if (res.status === 401) {
      config.onUnauthorized?.();
    }
    if (res.status === 204) {
      return { data: undefined as T, meta: null };
    }
    let body: Envelope<T>;
    try {
      body = (await res.json()) as Envelope<T>;
    } catch {
      throw new ApiError(res.status, `http_${res.status}`, `HTTP ${res.status}`);
    }
    return { data: unwrapEnvelope(res.status, body), meta: body.meta };
  }

  async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
    return (await requestWithMeta<T>(path, init)).data;
  }

  return { request, requestWithMeta };
}
