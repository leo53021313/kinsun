/** 長輩端 API。重點在 postTurn 的 query 參數——那是 2026-07-28 出過事的地方。 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  bindElderDevice,
  getTurnChunk,
  listElderNotifications,
  loginElder,
  logoutSession,
  postTurn,
} from "./api";

function mockFetch(data: unknown, status = 200) {
  const spy = vi
    .fn()
    .mockResolvedValue({ status, json: async () => ({ success: true, data, error: null, meta: null }) });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

const REPLY = { text: "好", audio_url: "", duration_ms: null, chunk_count: 1, reply_digest: "d" };

describe("長輩端 API", () => {
  it("綁定送 code", async () => {
    const spy = mockFetch({ elder_id: "e1", name: "王阿嬤", token: "t" });
    await bindElderDevice("AB12");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/device-bindings");
    expect(spy.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(spy.mock.calls[0][1].body as string)).toEqual({ code: "AB12" });
  });

  it("帳密登入送 phone 與 password", async () => {
    const spy = mockFetch({ elder_id: "e1", name: "王阿嬤", token: "t" });
    await loginElder("0912345678", "correct-horse-8");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elder-sessions");
    expect(spy.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(spy.mock.calls[0][1].body as string)).toEqual({
      phone: "0912345678",
      password: "correct-horse-8",
    });
  });

  it("登出用 DELETE 打 sessions，帶 Bearer（後端此端點長輩與家屬 token 皆可）", async () => {
    const spy = vi.fn().mockResolvedValue({ status: 204, json: async () => ({}) });
    vi.stubGlobal("fetch", spy);
    await expect(logoutSession("tok")).resolves.toBeUndefined();
    expect(spy.mock.calls[0][0]).toBe("/api/v1/sessions");
    expect(spy.mock.calls[0][1].method).toBe("DELETE");
    expect((spy.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer tok");
  });

  it("送出一輪時位置走 query，鍵名是 location 不是 place", async () => {
    // ⚠️ 2026-07-28 的實際故障：App 送 place、後端讀 location，位置從此沒寫進庫，
    // 而症狀只是「金孫每次問地點都反問您人在哪裡」——看起來像模型行為。
    const spy = mockFetch(REPLY);
    await postTurn(new ArrayBuffer(8), "tok", { place: "台南市", latitude: 22.99, longitude: 120.2 });
    const url = spy.mock.calls[0][0] as string;
    expect(url).toContain("location=");
    expect(url).toContain("latitude=22.99");
    expect(url).toContain("longitude=120.2");
    expect(url).not.toContain("place=");
  });

  it("沒有位置時完全不帶參數", async () => {
    // null＝「這輪沒有位置」，不是「他不在任何地方」。帶空字串會讓後端寫入空地名。
    const spy = mockFetch(REPLY);
    await postTurn(new ArrayBuffer(8), "tok", null);
    expect(spy.mock.calls[0][0]).toBe("/api/v1/turns");
  });

  it("送出一輪帶 Bearer 與音檔內容型別", async () => {
    const spy = mockFetch(REPLY);
    await postTurn(new ArrayBuffer(8), "tok", null);
    const init = spy.mock.calls[0][1];
    expect(init.method).toBe("POST");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer tok");
    expect((init.headers as Headers).get("Content-Type")).toBe("audio/m4a");
  });

  it("取後續語音段落時帶 digest", async () => {
    const spy = mockFetch({ audio_url: "", duration_ms: null, text: "" });
    await getTurnChunk(2, "abc123", "tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/turns/chunks/2?digest=abc123");
  });

  it("列長輩自己的提醒帶 token", async () => {
    const spy = mockFetch([{ content: "該吃血壓藥囉", created_at: 1 }]);
    const items = await listElderNotifications("tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elder-notifications");
    expect((spy.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer tok");
    expect(items).toEqual([{ content: "該吃血壓藥囉", created_at: 1 }]);
  });
});
