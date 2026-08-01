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
  listNotifications,
  listSchedules,
  loginGuardian,
  logoutGuardian,
  registerGuardian,
  revokeElderDeviceBindings,
  setElderAccount,
  updateSchedule,
} from "./api";

function mockFetch(data: unknown, status = 200, meta: unknown = null) {
  const spy = vi.fn().mockResolvedValue({ status, json: async () => ({ success: true, data, error: null, meta }) });
  vi.stubGlobal("fetch", spy);
  return spy;
}

/** 排程寫入回應的 data 形狀；三支測試共用。 */
const WRITTEN = {
  group_id: "g",
  kind: "custom",
  title: "散步",
  created_by: "guardian",
  event_at: null,
  occurrences: [],
};

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

  it("登入送 email 與 password 兩個鍵", async () => {
    const spy = mockFetch({ guardian_id: "g1", name: "兒子", token: "t" });
    await loginGuardian("a@example.com", "correct-horse-8");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/sessions");
    expect(spy.mock.calls[0][1].method).toBe("POST");
    expect(bodyOf(spy)).toEqual({ email: "a@example.com", password: "correct-horse-8" });
  });

  it("登出撤銷目前的 token，用 DELETE 打 sessions", async () => {
    const spy = vi.fn().mockResolvedValue({ status: 204, json: async () => ({}) });
    vi.stubGlobal("fetch", spy);
    await expect(logoutGuardian("tok")).resolves.toBeUndefined();
    expect(spy.mock.calls[0][0]).toBe("/api/v1/sessions");
    expect(spy.mock.calls[0][1].method).toBe("DELETE");
    expect((spy.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer tok");
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
    const spy = mockFetch({ invite_code: "CD34" });
    expect(await createGuardianInvite("e1", "tok")).toBe("CD34");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/guardian-invites");
    expect(spy.mock.calls[0][1].method).toBe("POST");
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
    const spy = mockFetch(WRITTEN);
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
    const spy = mockFetch(WRITTEN);
    await updateSchedule("e1", "g9", { kind: "custom", title: "散步", occurrences: [] }, "tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/schedules/g9");
    expect(spy.mock.calls[0][1].method).toBe("PUT");
    expect(bodyOf(spy)).toEqual({ kind: "custom", title: "散步", occurrences: [] });
  });

  // ⚠️ 這一組守的是 request → requestWithMeta 的那一步。`request` 只取 data、把 meta
  // 丟掉，改回去不會有任何型別錯誤或執行期例外——後端照樣講、前端就是聽不到，而唯一的
  // 症狀是家屬少看到一句話。
  it("建立排程把 meta.warnings 帶回來給呼叫端顯示", async () => {
    mockFetch(WRITTEN, 201, { warnings: ["回診前一天的提醒時間（08:00）已經過了。"] });
    const written = await createSchedule(
      "e1",
      { kind: "appointment", title: "回診", occurrences: [], event_date: "2026-08-02" },
      "tok",
    );
    expect(written.group.group_id).toBe("g");
    expect(written.warnings).toEqual(["回診前一天的提醒時間（08:00）已經過了。"]);
  });

  it("修改排程同樣把 meta.warnings 帶回來", async () => {
    mockFetch(WRITTEN, 200, { warnings: ["回診前一天的提醒時間（08:00）已經過了。"] });
    const written = await updateSchedule(
      "e1",
      "g9",
      { kind: "appointment", title: "回診", occurrences: [], event_date: "2026-08-02" },
      "tok",
    );
    expect(written.warnings).toEqual(["回診前一天的提醒時間（08:00）已經過了。"]);
  });

  it("meta 為 null（絕大多數情形）時 warnings 是空陣列，不是 undefined", async () => {
    // 呼叫端會直接 `.join("")`，給 undefined 會在成功路徑上炸掉整頁。
    mockFetch(WRITTEN, 201);
    const written = await createSchedule("e1", { kind: "custom", title: "散步", occurrences: [] }, "tok");
    expect(written.warnings).toEqual([]);
  });

  it("meta.warnings 混進非字串時逐項濾掉，不整包丟給畫面 render", async () => {
    // meta 的型別是 Record<string, unknown>，內容是網路來的資料；型別斷言只是叫編譯器
    // 閉嘴。真的收到物件時 React 會擲「Objects are not valid as a React child」整頁白。
    mockFetch(WRITTEN, 201, { warnings: ["真的話", 42, null, { code: "x" }] });
    const written = await createSchedule("e1", { kind: "custom", title: "散步", occurrences: [] }, "tok");
    expect(written.warnings).toEqual(["真的話"]);
  });

  it("meta.warnings 不是陣列時退回空陣列", async () => {
    mockFetch(WRITTEN, 201, { warnings: "一句話" });
    const written = await createSchedule("e1", { kind: "custom", title: "散步", occurrences: [] }, "tok");
    expect(written.warnings).toEqual([]);
  });

  it("刪除排程用 DELETE 且回應是 204 無內容", async () => {
    const spy = vi.fn().mockResolvedValue({ status: 204, json: async () => ({}) });
    vi.stubGlobal("fetch", spy);
    await expect(deleteSchedule("e1", "g9", "tok")).resolves.toBeUndefined();
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/schedules/g9");
    expect(spy.mock.calls[0][1].method).toBe("DELETE");
  });

  it("代辦長輩帳密用 PUT，送 phone 與 password", async () => {
    // ⚠️ 200＋`ok({elder_id})`，不是 204：後端 `elders.py` 的 `set_elder_account`
    // 回的是信封。假回應與後端實況不符時，測試守的是一個不存在的世界——204 那條
    // 路在共用 client 裡是提早 return，根本沒走到解信封。
    const spy = mockFetch({ elder_id: "e1" });
    await setElderAccount("e1", "0912345678", "correct-horse-8", "tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/account");
    expect(spy.mock.calls[0][1].method).toBe("PUT");
    expect(bodyOf(spy)).toEqual({ phone: "0912345678", password: "correct-horse-8" });
  });

  it("重新產生長輩綁定碼用 DELETE 打 device-bindings，回的是新的碼本身", async () => {
    // 後端這支刻意回 200＋新碼而不是 204：重綁流程需要新碼，省一次額外請求。
    const spy = mockFetch({ invite_code: "NEW123" });
    expect(await revokeElderDeviceBindings("e1", "tok")).toBe("NEW123");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/elders/e1/device-bindings");
    expect(spy.mock.calls[0][1].method).toBe("DELETE");
    expect((spy.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer tok");
  });

  it("列 App 內通知帶 token", async () => {
    // ⚠️ 補審查發現的 Minor 3：長輩端對稱的 listElderNotifications 早有這條
    // method／URL 斷言（elder/api.test.ts），家屬端這支自 P2 起就沒有——而
    // notify/useNotificationFeed.ts（P4 Task 2）是它上線後最高頻的呼叫端，
    // 每兩秒打一次。鍵名／路徑打錯的症狀是後端安靜地收到空值或 404，同
    // 2026-07-28 對講機定位失效那種「測試全綠、功能早就壞了」的失效形狀。
    const spy = mockFetch([{ content: "該吃血壓藥囉", created_at: 1 }]);
    const items = await listNotifications("tok");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/notifications");
    expect((spy.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer tok");
    expect(items).toEqual([{ content: "該吃血壓藥囉", created_at: 1 }]);
  });
});
