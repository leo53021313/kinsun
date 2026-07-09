/**
 * 後端 API 呼叫端：所有 JSON 欄位 snake_case，與後端完全同鍵名。
 * base URL 由 EXPO_PUBLIC_API_URL 提供（見 .env.example）。
 */

export type Elder = { elder_id: string; name: string };
export type CreatedElder = Elder & { invite_code: string };
export type Medication = { medication_id: string; name: string; slots: string[] };
export type Appointment = { appointment_id: string; date: string; label: string };
export type HealthReport = {
  risk_events: { tier: number; reason: string; created_at: number }[];
  reminders: { kind: string; content: string; created_at: number }[];
};
export type AppNotification = { content: string; created_at: number };
export type GuardianSession = { guardian_id: string; name: string; token: string };
export type ElderSession = { elder_id: string; name: string; token: string };
export type TurnReply = { text: string; audio_url: string; duration_ms: number | null };

const BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<T> {
  if (!BASE_URL) {
    throw new ApiError(0, "尚未設定 EXPO_PUBLIC_API_URL（見 app/.env.example）");
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
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // 非 JSON 錯誤 body：保留 HTTP 狀態描述。
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

// --- App 認證 ---

export function registerGuardian(
  email: string,
  password: string,
  name: string,
): Promise<GuardianSession> {
  return request("/api/app/guardians", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
}

export function loginGuardian(email: string, password: string): Promise<GuardianSession> {
  return request("/api/app/sessions", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function bindElderDevice(code: string): Promise<ElderSession> {
  return request("/api/app/device-bindings", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

// --- 家屬端：App 內通知（✅ D-12） ---

export async function listNotifications(token: string): Promise<AppNotification[]> {
  const body = await request<{ notifications: AppNotification[] }>("/api/app/notifications", {
    token,
  });
  return body.notifications;
}

// --- 長輩端：對講機回合 ---

export async function postTurn(audioUri: string, token: string): Promise<TurnReply> {
  const audio = await (await fetch(audioUri)).blob();
  return request("/api/app/turns", {
    method: "POST",
    body: audio,
    headers: { "Content-Type": "audio/m4a" },
    token,
  });
}

// --- 家屬端 REST（App token 認證） ---

export async function listElders(token: string): Promise<Elder[]> {
  const body = await request<{ elders: Elder[] }>("/api/me/elders", { token });
  return body.elders;
}

export function createElder(name: string, token: string): Promise<CreatedElder> {
  return request("/api/elders", { method: "POST", body: JSON.stringify({ name }), token });
}

export async function createGuardianInvite(elderId: string, token: string): Promise<string> {
  const body = await request<{ invite_code: string }>(
    `/api/elders/${elderId}/guardian-invites`,
    { method: "POST", token },
  );
  return body.invite_code;
}

export async function listMedications(elderId: string, token: string): Promise<Medication[]> {
  const body = await request<{ medications: Medication[] }>(
    `/api/elders/${elderId}/medications`,
    { token },
  );
  return body.medications;
}

export async function listAppointments(elderId: string, token: string): Promise<Appointment[]> {
  const body = await request<{ appointments: Appointment[] }>(
    `/api/elders/${elderId}/appointments`,
    { token },
  );
  return body.appointments;
}

export function getHealthReport(elderId: string, token: string): Promise<HealthReport> {
  return request(`/api/elders/${elderId}/health-report`, { token });
}
