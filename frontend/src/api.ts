/**
 * LIFF 端 API 呼叫端（乙-5）：/api/v1＋統一信封解包；型別與錯誤來自 kinsun-shared 共用包。
 * 認證：LIFF idToken（隨 LINE 凍結，退場時移除，ADR-009）。
 */

import liff from "@line/liff";

import { createApiClient } from "kinsun-shared/client";
import { ApiError } from "kinsun-shared/envelope";
import type {
  CreatedElder,
  Elder,
  HealthReport,
  ReminderItem,
  RiskEventItem,
  ScheduleGroup,
  ScheduleInput,
} from "kinsun-shared/types";

export { ApiError };
export type { Elder, ReminderItem, RiskEventItem, ScheduleGroup, ScheduleInput };

// 共同流程住共用包（✅ 庚-30）；LIFF 差異只有「認證頭＝LINE ID token」。
const client = createApiClient({
  authHeaders: () => {
    const token = liff.getIDToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  },
});

const apiFetch = client.request;

export function listElders(): Promise<Elder[]> {
  return apiFetch("/api/v1/elders");
}

/** 統一排程（D-76 P3）：用藥、回診與長輩自訂共用一支資源，操作單位是 group。 */
export function listSchedules(elderId: string, kind?: ScheduleGroup["kind"]): Promise<ScheduleGroup[]> {
  const query = kind ? `?kind=${kind}` : "";
  return apiFetch(`/api/v1/elders/${elderId}/schedules${query}`);
}

export async function addSchedule(elderId: string, body: ScheduleInput): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/schedules`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateSchedule(
  elderId: string,
  groupId: string,
  body: ScheduleInput,
): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/schedules/${groupId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteSchedule(elderId: string, groupId: string): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/schedules/${groupId}`, { method: "DELETE" });
}

export function createElder(elderName: string): Promise<CreatedElder> {
  return apiFetch("/api/v1/elders", {
    method: "POST",
    body: JSON.stringify({ name: elderName }),
  });
}

export function generateGuardianInvite(elderId: string): Promise<{ invite_code: string }> {
  return apiFetch(`/api/v1/elders/${elderId}/guardian-invites`, { method: "POST" });
}

export function getHealthReport(elderId: string): Promise<HealthReport> {
  return apiFetch(`/api/v1/elders/${elderId}/health-report`);
}
