/**
 * 後端 API 呼叫端（乙-5）：/api/v1＋統一信封解包；型別與錯誤來自 kinsun-shared 共用包。
 * 所有 JSON 欄位 snake_case，與後端完全同鍵名。base URL 由 EXPO_PUBLIC_API_URL 提供。
 */

import { ApiError, type Envelope, unwrapEnvelope } from "kinsun-shared/envelope";
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
  TurnReply,
};

const BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? "").replace(/\/$/, "");

async function request<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<T> {
  if (!BASE_URL) {
    throw new ApiError(0, "missing_base_url", "尚未設定 EXPO_PUBLIC_API_URL（見 app/.env.example）");
  }
  const headers: Record<string, string> = {
    ...(init.body !== undefined && !(init.headers as Record<string, string>)?.["Content-Type"]
      ? { "Content-Type": "application/json" }
      : {}),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (init.token) {
    headers.Authorization = `Bearer ${init.token}`;
  }
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (res.status === 204) {
    return undefined as T;
  }
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, `http_${res.status}`, `HTTP ${res.status}`);
  }
  return unwrapEnvelope(res.status, body);
}

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

export async function postTurn(audioUri: string, token: string): Promise<TurnReply> {
  const audio = await (await fetch(audioUri)).blob();
  return request("/api/v1/turns", {
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

/** 每日摘要（✅ D-09 己-3）：家屬可看摘要、不開放逐字對話。 */
export function listDailySummaries(
  elderId: string,
  token: string,
  limit = 14,
): Promise<DailySummary[]> {
  return request(`/api/v1/elders/${elderId}/daily-summaries?limit=${limit}`, { token });
}
