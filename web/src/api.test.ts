/** API 呼叫端：同源相對路徑、信封解包、Bearer token 注入。 */

import { ApiError } from "kinsun-shared/envelope";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiErrorMessage, getDemoStatus, request } from "./api";

function mockFetch(body: unknown, status = 200) {
  const spy = vi.fn().mockResolvedValue({
    status,
    json: async () => body,
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("走同源相對路徑，不帶任何主機名", async () => {
    const spy = mockFetch({
      success: true,
      data: { overall: "available", components: {} },
      error: null,
      meta: null,
    });
    await getDemoStatus();
    expect(spy.mock.calls[0][0]).toBe("/api/v1/demo-status");
  });

  it("解開信封只回 data", async () => {
    mockFetch({
      success: true,
      data: { overall: "degraded", components: { tts: "down" } },
      error: null,
      meta: null,
    });
    const status = await getDemoStatus();
    expect(status.overall).toBe("degraded");
    expect(status.components.tts).toBe("down");
  });

  it("失敗的信封擲出帶繁中訊息的 ApiError", async () => {
    mockFetch(
      { success: false, data: null, error: { code: "not_found", message: "找不到這個頁面" }, meta: null },
      404,
    );
    await expect(getDemoStatus()).rejects.toThrow(ApiError);
    await expect(getDemoStatus()).rejects.toThrow("找不到這個頁面");
  });

  it("有 token 時掛上 Bearer 標頭", async () => {
    const spy = mockFetch({ success: true, data: {}, error: null, meta: null });
    await request("/api/v1/notifications", { token: "abc123" });
    const headers = spy.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer abc123");
  });

  it("沒有 token 時不掛 Authorization", async () => {
    const spy = mockFetch({ success: true, data: {}, error: null, meta: null });
    await request("/api/v1/meta");
    const headers = spy.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBeNull();
  });
});

describe("apiErrorMessage", () => {
  // ⚠️ 後端回應不是合法 JSON 時（隧道抖動的 502 HTML、未捕捉例外的 500
  // text/plain），shared/client.ts 會自造 `http_<status>` 開頭的 code、訊息是
  // 英文字面值（如 `HTTP 502`）——這種訊息不可直接顯示給使用者看。這是本工項要
  // 修的失效情境，用 json() 直接擲例外重現。
  it("json() 直接擲例外（後端回應不是合法 JSON）時，退回呼叫端指定的預設訊息，不顯示英文字面值", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 502,
        json: async () => {
          throw new SyntaxError("Unexpected token '<'");
        },
      }),
    );
    let caught: unknown;
    try {
      await getDemoStatus();
    } catch (exc) {
      caught = exc;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe("http_502");
    expect(apiErrorMessage(caught, "連線失敗，請稍後再試。")).toBe("連線失敗，請稍後再試。");
  });

  it("後端真的解出信封、帶著繁中訊息時，照實顯示", () => {
    const exc = new ApiError(404, "not_found", "找不到這個頁面");
    expect(apiErrorMessage(exc, "連線失敗，請稍後再試。")).toBe("找不到這個頁面");
  });

  it("非 ApiError 的例外（如 fetch 自己擲的 TypeError）退回預設訊息", () => {
    expect(apiErrorMessage(new TypeError("Failed to fetch"), "連線失敗，請稍後再試。")).toBe(
      "連線失敗，請稍後再試。",
    );
  });
});
