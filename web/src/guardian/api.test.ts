/**
 * 家屬端 API 呼叫端。
 *
 * 測的是**線路契約**：路徑、方法、以及送出去的 JSON 鍵名。鍵名打錯的症狀是
 * 後端安靜地收到空值（2026-07-28 對講機定位失效就是這樣——App 送 place、後端
 * 讀 location，位置從此沒寫進庫過），所以每一支寫入端點都斷言 body。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createElder,
  createGuardianInvite,
  createSchedule,
  deleteSchedule,
  listElders,
  listSchedules,
  loginGuardian,
  registerGuardian,
  setElderAccount,
  updateSchedule,
} from "./api";

function mockFetch(data: unknown, status = 200) {
  const spy = vi.fn().mockResolvedValue({ status, json: async () => ({ success: true, data, error: null, meta: null }) });
  vi.stubGlobal("fetch", spy);
  return spy;
}

function bodyOf(spy: ReturnType<typeof vi.fn>): Record<string, unknown> {
  return JSON.parse(spy.mock.calls[0][1].body as string);
}

afterEach(() => vi.unstubAllGlobals());

describe("家屬端 API", () => {
  it("註冊送 email／password／name 三個鍵", async () => {
    const spy = mockFetch({ guardian_id: "g1", name: "兒子", token: "t" });
    await registerGuardian("a@example.com", "correct-horse-8", "兒子");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/guardians");
    expect(spy.mock.calls[0][1].method).toBe("POST");
    expect(bodyOf(spy)).toEqual({
      email: "a@example.com",
      password: "correct-horse-8",
      name: "兒子",
    });
  });

  it("登入打 sessions", async () => {
    const spy = mockFetch({ guardian_id: "g1", name: "兒子", token: "t" });
    await loginGuardian("a@example.com", "correct-horse-8");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/sessions");
  });

  it("列長輩帶 token", async () => {
    const spy = mockFetch([]);
    await listElders("tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders");
    expect((spy.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer tok");
  });

  it("建立長輩只送 name", async () => {
    const spy = mockFetch({ elder_id: "e1", name: "阿嬤", nickname: "", invite_code: "AB12" });
    const created = await createElder("阿嬤", "tok");
    expect(bodyOf(spy)).toEqual({ name: "阿嬤" });
    expect(created.invite_code).toBe("AB12");
  });

  it("產生家屬邀請碼回的是碼本身，不是整包物件", async () => {
    mockFetch({ invite_code: "CD34" });
    expect(await createGuardianInvite("e1", "tok")).toBe("CD34");
  });

  it("列排程可以帶類型篩選", async () => {
    const spy = mockFetch([]);
    await listSchedules("e1", "tok", "medication");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/schedules?kind=medication");
  });

  it("不帶類型時不加 query", async () => {
    const spy = mockFetch([]);
    await listSchedules("e1", "tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/schedules");
  });

  it("建立排程送的鍵名與後端 ScheduleIn 完全一致", async () => {
    const spy = mockFetch({ group_id: "g", kind: "custom", title: "散步", created_by: "guardian", event_at: null, occurrences: [] });
    await createSchedule(
      "e1",
      { kind: "custom", title: "散步", occurrences: [{ repeat: "daily", time: "17:00" }] },
      "tok",
    );
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/schedules");
    expect(bodyOf(spy)).toEqual({
      kind: "custom",
      title: "散步",
      occurrences: [{ repeat: "daily", time: "17:00" }],
    });
  });

  it("修改排程用 PUT，路徑帶 group_id", async () => {
    const spy = mockFetch({ group_id: "g", kind: "custom", title: "散步", created_by: "guardian", event_at: null, occurrences: [] });
    await updateSchedule("e1", "g9", { kind: "custom", title: "散步", occurrences: [] }, "tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/schedules/g9");
    expect(spy.mock.calls[0][1].method).toBe("PUT");
  });

  it("刪除排程用 DELETE 且回應是 204 無內容", async () => {
    const spy = vi.fn().mockResolvedValue({ status: 204, json: async () => ({}) });
    vi.stubGlobal("fetch", spy);
    await expect(deleteSchedule("e1", "g9", "tok")).resolves.toBeUndefined();
    expect(spy.mock.calls[0][1].method).toBe("DELETE");
  });

  it("代辦長輩帳密用 PUT，送 phone 與 password", async () => {
    const spy = vi.fn().mockResolvedValue({ status: 204, json: async () => ({}) });
    vi.stubGlobal("fetch", spy);
    await setElderAccount("e1", "0912345678", "correct-horse-8", "tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/account");
    expect(spy.mock.calls[0][1].method).toBe("PUT");
    expect(bodyOf(spy)).toEqual({ phone: "0912345678", password: "correct-horse-8" });
  });
});
