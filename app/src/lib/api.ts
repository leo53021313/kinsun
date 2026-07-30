/**
 * 後端 API 呼叫端（乙-5）：/api/v1＋統一信封解包；型別與錯誤來自 kinsun-shared 共用包。
 * 所有 JSON 欄位 snake_case，與後端完全同鍵名。base URL 由 EXPO_PUBLIC_API_URL 提供。
 */

import { createApiClient } from "kinsun-shared/client";
import { ApiError } from "kinsun-shared/envelope";

import type { ElderPlace } from "@/lib/location";
import type {
  AppNotification,
  CreatedElder,
  DailySummary,
  Elder,
  ElderSession,
  GuardianSession,
  HealthReport,
  ScheduleGroup,
  ScheduleInput,
  Meta,
  TurnChunk,
  TurnReply,
} from "kinsun-shared/types";

export { ApiError };
export type {
  AppNotification,
  CreatedElder,
  DailySummary,
  Elder,
  ElderSession,
  GuardianSession,
  HealthReport,
  ScheduleGroup,
  ScheduleInput,
  Meta,
  TurnChunk,
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

// --- 兩端共用：裝置推播 token（真推播 D-08 階段 5，2026-07-29） ---

/** 登記這台裝置。主體由 token 決定——不送 principal_id，伺服器也不會看。 */
export function registerPushToken(
  sessionToken: string,
  token: string,
  platform: "android" | "ios",
): Promise<{ registered: boolean }> {
  return request("/api/v1/push-tokens", {
    token: sessionToken,
    method: "POST",
    body: JSON.stringify({ token, platform }),
  });
}

/** 登出前清掉，避免提醒繼續推到已經不是本人在用的裝置。 */
export function removePushToken(sessionToken: string, token: string): Promise<void> {
  return request(`/api/v1/push-tokens/${encodeURIComponent(token)}`, {
    token: sessionToken,
    method: "DELETE",
  });
}

// --- 長輩端：App 內通知（X-01，2026-07-29） ---

/** 長輩讀自己的用藥／回診提醒與主動關懷。真推播到位後仍是推不到時的補拉路徑。 */
export function listElderNotifications(token: string): Promise<AppNotification[]> {
  return request("/api/v1/elder-notifications", { token });
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

/**
 * 取回覆的第 index 段語音（分段串流；第 0 段已隨 postTurn 回過）。
 *
 * digest 讓伺服器確認取的是同一輪的回覆——長輩若在播放中又講了一句，這裡會回 409，
 * 呼叫端應停止續拉，否則會把新回覆的句子接在舊回覆後面播出去。
 */
export function getTurnChunk(index: number, digest: string, token: string): Promise<TurnChunk> {
  return request(`/api/v1/turns/chunks/${index}?digest=${encodeURIComponent(digest)}`, { token });
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

/** 統一排程（D-76 P3）：用藥、回診、長輩自訂共用一支資源，操作單位是 group。 */
export function listSchedules(
  elderId: string,
  token: string,
  kind?: ScheduleGroup["kind"],
): Promise<ScheduleGroup[]> {
  const query = kind ? `?kind=${kind}` : "";
  return request(`/api/v1/elders/${elderId}/schedules${query}`, { token });
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

export function deleteSchedule(
  elderId: string,
  groupId: string,
  token: string,
): Promise<void> {
  return request(`/api/v1/elders/${elderId}/schedules/${groupId}`, {
    method: "DELETE",
    token,
  });
}
