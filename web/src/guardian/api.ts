/**
 * 家屬端用到的端點。共同流程住 `@/api`（信封、Bearer、同源）。
 *
 * ⚠️ 送出去的 JSON 鍵名必須與後端逐字相同。鍵名打錯的症狀是後端安靜地收到
 * 空值——2026-07-28 對講機定位失效就是這樣（App 送 place、後端讀 location，
 * 位置從此沒寫進庫過，而金孫只是變得每次都反問「您人在哪裡」）。
 */

import type {
  AppNotification,
  CreatedElder,
  DailySummary,
  Elder,
  GuardianSession,
  HealthReport,
  ScheduleGroup,
  ScheduleInput,
} from "kinsun-shared/types";

import { request } from "@/api";

export function registerGuardian(
  email: string,
  password: string,
  name: string,
): Promise<GuardianSession> {
  return request("/api/v1/guardians", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
}

export function loginGuardian(email: string, password: string): Promise<GuardianSession> {
  return request("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

/** 登出＝撤銷這一個 token（✅ D-25）。失敗不擋本機登出，呼叫端自行忽略。 */
export function logoutGuardian(token: string): Promise<void> {
  return request("/api/v1/sessions", { method: "DELETE", token });
}

export function listElders(token: string): Promise<Elder[]> {
  return request("/api/v1/elders", { token });
}

export function createElder(name: string, token: string): Promise<CreatedElder> {
  return request("/api/v1/elders", { method: "POST", body: JSON.stringify({ name }), token });
}

export async function createGuardianInvite(elderId: string, token: string): Promise<string> {
  const body = await request<{ invite_code: string }>(
    `/api/v1/elders/${elderId}/guardian-invites`,
    { method: "POST", token },
  );
  return body.invite_code;
}

/**
 * 撤銷長輩已綁定的裝置並取得一組新的長輩綁定碼（✅ D-25 修訂）。
 *
 * ⚠️ 動詞取 `revoke` 而非 `delete`（`deleteSchedule` 那種 REST 慣例）：後端這支
 * handler 自己就叫 `revoke_device_bindings`，專案在這條端點上早已做過同一個判斷
 * ——它不是單純的刪除。它撤掉該長輩全部 token＋拆掉 App 通道綁定的**同時**發一組
 * 新的綁定碼，並以 200＋`{invite_code}` 回來（刻意不是 204，重綁流程需要新碼、
 * 省一次往返）。取名只講「重新產生綁定碼」會讓呼叫端看不出長輩手機會被登出，
 * 而那正是這支端點最需要被看見的那一半。
 *
 * 回的是碼本身、不是整包物件，與 `createGuardianInvite` 一致。
 */
export async function revokeElderDeviceBindings(
  elderId: string,
  token: string,
): Promise<string> {
  const body = await request<{ invite_code: string }>(
    `/api/v1/elders/${elderId}/device-bindings`,
    { method: "DELETE", token },
  );
  return body.invite_code;
}

/** 統一排程（D-76 P3）：用藥、回診與長輩自訂共用一支資源，操作單位是 group。 */
export function listSchedules(
  elderId: string,
  token: string,
  kind?: ScheduleGroup["kind"],
): Promise<ScheduleGroup[]> {
  return request(`/api/v1/elders/${elderId}/schedules${kind ? `?kind=${kind}` : ""}`, { token });
}

export function createSchedule(
  elderId: string,
  body: ScheduleInput,
  token: string,
): Promise<ScheduleGroup> {
  return request(`/api/v1/elders/${elderId}/schedules`, {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });
}

export function updateSchedule(
  elderId: string,
  groupId: string,
  body: ScheduleInput,
  token: string,
): Promise<ScheduleGroup> {
  return request(`/api/v1/elders/${elderId}/schedules/${groupId}`, {
    method: "PUT",
    body: JSON.stringify(body),
    token,
  });
}

export function deleteSchedule(elderId: string, groupId: string, token: string): Promise<void> {
  return request(`/api/v1/elders/${elderId}/schedules/${groupId}`, { method: "DELETE", token });
}

export function getHealthReport(elderId: string, token: string): Promise<HealthReport> {
  return request(`/api/v1/elders/${elderId}/health-report`, { token });
}

/** 每日摘要（✅ D-09 己-3）：家屬看得到摘要，看不到逐字對話。 */
export function listDailySummaries(
  elderId: string,
  token: string,
  limit = 14,
): Promise<DailySummary[]> {
  return request(`/api/v1/elders/${elderId}/daily-summaries?limit=${limit}`, { token });
}

/** 代辦長輩帳密（✅ D-71 己-6）：PUT＝重呼即重設密碼／換號碼。 */
export async function setElderAccount(
  elderId: string,
  phone: string,
  password: string,
  token: string,
): Promise<void> {
  await request(`/api/v1/elders/${elderId}/account`, {
    method: "PUT",
    body: JSON.stringify({ phone, password }),
    token,
  });
}

export function listNotifications(token: string): Promise<AppNotification[]> {
  return request("/api/v1/notifications", { token });
}
