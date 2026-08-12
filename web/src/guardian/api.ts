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
  VoiceProfileScript,
  VoiceProfileStatus,
} from "kinsun-shared/types";

import { request, requestWithMeta } from "@/api";

/**
 * 排程寫入的結果：建好的那一組，外加**後端要對家屬說的話**。
 *
 * `warnings` 不是錯誤——寫入是成功的。它目前唯一的內容是「回診前一天那顆提醒的
 * 時刻已經過了，只建了當天那顆」（06 §5）。這件事不講，家屬沒有任何地方會發現：
 * 回診清單顯示的單位是「一件事」，不逐顆列鬧鐘。
 */
export type ScheduleWriteResult = {
  group: ScheduleGroup;
  /** 可直接顯示的繁中人話，逐條列出；沒有話要說時是空陣列。 */
  warnings: string[];
};

/**
 * 從信封的 `meta` 取出 `warnings`。
 *
 * ⚠️ 逐項檢查型別而不是 `as string[]`：`meta` 在共用包裡的型別是
 * `Record<string, unknown>`，內容是**網路來的資料**，型別斷言只是叫編譯器閉嘴。
 * 真的收到非字串時寧可少顯示一則，也不要讓 React 拿著一個物件去 render。
 */
function warningsOf(meta: Record<string, unknown> | null): string[] {
  const raw = meta?.warnings;
  return Array.isArray(raw) ? raw.filter((item): item is string => typeof item === "string") : [];
}

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

/**
 * 更改金孫對這位長輩的人設（2026-08-05）。回傳後端實際採用的值。
 *
 * ⚠️ 後端刻意另開一支端點、不併進改稱謂的 `/profile`：那支是整份 upsert，
 * 少帶 nickname 就會把稱謂洗掉。前端這裡同樣只送人設一格。
 */
export async function setElderPersona(
  elderId: string,
  persona: string,
  token: string,
): Promise<string> {
  const body = await request<{ persona: string }>(`/api/v1/elders/${elderId}/persona`, {
    method: "PUT",
    body: JSON.stringify({ persona }),
    token,
  });
  return body.persona;
}

/** 統一排程（D-76 P3）：用藥、回診與長輩自訂共用一支資源，操作單位是 group。 */
export function listSchedules(
  elderId: string,
  token: string,
  kind?: ScheduleGroup["kind"],
): Promise<ScheduleGroup[]> {
  return request(`/api/v1/elders/${elderId}/schedules${kind ? `?kind=${kind}` : ""}`, { token });
}

export async function createSchedule(
  elderId: string,
  body: ScheduleInput,
  token: string,
): Promise<ScheduleWriteResult> {
  const { data, meta } = await requestWithMeta<ScheduleGroup>(
    `/api/v1/elders/${elderId}/schedules`,
    { method: "POST", body: JSON.stringify(body), token },
  );
  return { group: data, warnings: warningsOf(meta) };
}

export async function updateSchedule(
  elderId: string,
  groupId: string,
  body: ScheduleInput,
  token: string,
): Promise<ScheduleWriteResult> {
  const { data, meta } = await requestWithMeta<ScheduleGroup>(
    `/api/v1/elders/${elderId}/schedules/${groupId}`,
    { method: "PUT", body: JSON.stringify(body), token },
  );
  return { group: data, warnings: warningsOf(meta) };
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

// --- 長輩客製化聲音（2026-08-12）：家屬錄一段參考語音，長輩往後聽到那個聲音 ---

/**
 * 取家屬要照唸的稿子與注意事項。
 *
 * 不帶 token 是刻意的：後端這支沒有認證依賴（稿子本身不是機密），多送一個標頭
 * 只會讓「這支到底要不要登入」在前後端各有一種說法。
 */
export function getVoiceProfileScript(): Promise<VoiceProfileScript> {
  return request("/api/v1/voice-profile-script");
}

/** 查這位長輩目前有沒有生效中的客製化聲音。⚠️ 後端不回音檔，也不回可下載網址。 */
export function getVoiceProfile(elderId: string, token: string): Promise<VoiceProfileStatus> {
  return request(`/api/v1/elders/${elderId}/voice-profile`, { token });
}

/**
 * 上傳參考音檔，設定或覆蓋這位長輩的專屬聲音。
 *
 * ⚠️ 三樣東西各有各的位置，放錯的症狀都不一樣：音檔是**原始位元組**放 body
 * （不是 multipart）、`consented_by` 走 **query param**（body 已被音檔佔滿）、
 * 格式走 **Content-Type**（後端據此擋掉非音檔，且它會成為 Supabase 上物件的
 * 中繼資料）。
 */
export function setVoiceProfile(
  elderId: string,
  audio: ArrayBuffer,
  mimeType: string,
  consentedBy: string,
  token: string,
): Promise<VoiceProfileStatus> {
  const query = new URLSearchParams({ consented_by: consentedBy }).toString();
  return request(`/api/v1/elders/${elderId}/voice-profile?${query}`, {
    method: "PUT",
    body: audio,
    headers: { "Content-Type": mimeType },
    token,
  });
}

/** 撤銷客製化聲音，下一輪起回到全域預設聲音。 */
export function revokeVoiceProfile(elderId: string, token: string): Promise<void> {
  return request(`/api/v1/elders/${elderId}/voice-profile`, { method: "DELETE", token });
}
