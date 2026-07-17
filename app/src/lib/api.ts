/**
 * 後端 API 呼叫端（乙-5）：/api/v1＋統一信封解包；型別與錯誤來自 kinsun-shared 共用包。
 * 所有 JSON 欄位 snake_case，與後端完全同鍵名。base URL 由 EXPO_PUBLIC_API_URL 提供。
 */

import { createApiClient } from "kinsun-shared/client";
import { ApiError } from "kinsun-shared/envelope";

import type { ElderPlace } from "@/lib/location";
import type {
  AppNotification,
  Appointment,
  CreatedElder,
  DailySummary,
  Elder,
  ElderSession,
  GuardianSession,
  HealthReport,
  Medication,
  Meta,
  TurnReply,
} from "kinsun-shared/types";

export { ApiError };
export type {
  AppNotification,
  Appointment,
  CreatedElder,
  DailySummary,
  Elder,
  ElderSession,
  GuardianSession,
  HealthReport,
  Medication,
  Meta,
  TurnReply,
};

const BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? "").replace(/\/$/, "");

// 共同流程（信封／204／錯誤）住共用包（✅ 庚-30）；此處只注入 App 端差異。
const client = createApiClient({
  baseUrl: () => {
    if (!BASE_URL) {
      throw new ApiError(
        0,
        "missing_base_url",
        "尚未設定 EXPO_PUBLIC_API_URL（見 app/.env.example）",
      );
    }
    return BASE_URL;
  },
  authHeaders: (token) => {
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  },
});

const request = client.request;

// --- App 認證 ---

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

/** 登出＝撤銷當前 token（✅ D-25 修訂）；失敗不擋本機登出，呼叫端自行忽略錯誤。 */
/** 家屬與長輩共用（✅ 庚-42：長輩自助登出）：撤銷當前 token。 */
export function logoutSession(token: string): Promise<void> {
  return request("/api/v1/sessions", { method: "DELETE", token });
}

export function logoutGuardian(token: string): Promise<void> {
  return request("/api/v1/sessions", { method: "DELETE", token });
}

export function bindElderDevice(code: string): Promise<ElderSession> {
  return request("/api/v1/device-bindings", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

// --- 家屬端：App 內通知（✅ D-12） ---

export function listNotifications(token: string): Promise<AppNotification[]> {
  return request("/api/v1/notifications", { token });
}

// --- 長輩端：對講機回合 ---

export async function postTurn(
  audioUri: string,
  token: string,
  place: ElderPlace | null = null,
): Promise<TurnReply> {
  const audio = await (await fetch(audioUri)).blob();
  // 地名與座標走 query param：/turns 收的是裸音檔 body，它們在 body 裡沒有位置可放。
  // null＝這輪沒有位置（未授權、室內收不到），不帶參數——不是「他不在任何地方」。
  const query = place
    ? `?${new URLSearchParams({
        location: place.place,
        latitude: String(place.latitude),
        longitude: String(place.longitude),
      })}`
    : "";
  return request(`/api/v1/turns${query}`, {
    method: "POST",
    body: audio,
    headers: { "Content-Type": "audio/m4a" },
    token,
  });
}

// --- 家屬端 REST（App token 認證） ---

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

/** 作廢長輩裝置並取得新綁定碼（✅ D-25 修訂：換機／裝置遺失時用）。 */
export async function revokeElderDevice(elderId: string, token: string): Promise<string> {
  const body = await request<{ invite_code: string }>(
    `/api/v1/elders/${elderId}/device-bindings`,
    { method: "DELETE", token },
  );
  return body.invite_code;
}

export function listMedications(elderId: string, token: string): Promise<Medication[]> {
  return request(`/api/v1/elders/${elderId}/medications`, { token });
}

export function listAppointments(elderId: string, token: string): Promise<Appointment[]> {
  return request(`/api/v1/elders/${elderId}/appointments`, { token });
}

export function getHealthReport(elderId: string, token: string): Promise<HealthReport> {
  return request(`/api/v1/elders/${elderId}/health-report`, { token });
}

/** 長輩帳密登入（✅ D-71 己-6）：帳號＝手機號碼；只管重登，未配對回 403 not_paired。 */
export function loginElder(phone: string, password: string): Promise<ElderSession> {
  return request("/api/v1/elder-sessions", {
    method: "POST",
    body: JSON.stringify({ phone, password }),
  });
}

/** 家屬代辦長輩帳密（✅ D-71 己-6）：PUT＝重呼即重設密碼／換號碼。 */
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

// --- 公開 meta（內測模式下發，spec 2026-07-12） ---

export function getMeta(): Promise<Meta> {
  return request("/api/v1/meta");
}

/** 每日摘要（✅ D-09 己-3）：家屬可看摘要、不開放逐字對話。 */
export function listDailySummaries(
  elderId: string,
  token: string,
  limit = 14,
): Promise<DailySummary[]> {
  return request(`/api/v1/elders/${elderId}/daily-summaries?limit=${limit}`, { token });
}

// --- 家屬端：用藥／回診管理（App 版編輯，對接既有 CRUD 端點） ---

export function createMedication(
  elderId: string,
  name: string,
  slots: string[],
  token: string,
): Promise<Medication> {
  return request(`/api/v1/elders/${elderId}/medications`, {
    method: "POST",
    body: JSON.stringify({ name, slots }),
    token,
  });
}

export function updateMedication(
  elderId: string,
  medicationId: string,
  name: string,
  slots: string[],
  token: string,
): Promise<Medication> {
  return request(`/api/v1/elders/${elderId}/medications/${medicationId}`, {
    method: "PUT",
    body: JSON.stringify({ name, slots }),
    token,
  });
}

export function deleteMedication(
  elderId: string,
  medicationId: string,
  token: string,
): Promise<void> {
  return request(`/api/v1/elders/${elderId}/medications/${medicationId}`, {
    method: "DELETE",
    token,
  });
}

export function createAppointment(
  elderId: string,
  date: string,
  label: string,
  time: string,
  token: string,
): Promise<Appointment> {
  return request(`/api/v1/elders/${elderId}/appointments`, {
    method: "POST",
    body: JSON.stringify({ date, label, time }),
    token,
  });
}

export function updateAppointment(
  elderId: string,
  appointmentId: string,
  date: string,
  label: string,
  time: string,
  token: string,
): Promise<Appointment> {
  return request(`/api/v1/elders/${elderId}/appointments/${appointmentId}`, {
    method: "PUT",
    body: JSON.stringify({ date, label, time }),
    token,
  });
}

export function deleteAppointment(
  elderId: string,
  appointmentId: string,
  token: string,
): Promise<void> {
  return request(`/api/v1/elders/${elderId}/appointments/${appointmentId}`, {
    method: "DELETE",
    token,
  });
}
