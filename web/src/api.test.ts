/** API 呼叫端：同源相對路徑、信封解包、Bearer token 注入。 */

import { ApiError } from "kinsun-shared/envelope";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getDemoStatus, request } from "./api";

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
