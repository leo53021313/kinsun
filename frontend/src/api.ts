/**
 * LIFF 端 API 呼叫端（乙-5）：/api/v1＋統一信封解包；型別與錯誤來自 kinsun-shared 共用包。
 * 認證：LIFF idToken（隨 LINE 凍結，退場時移除，ADR-009）。
 */

import liff from "@line/liff";

import { createApiClient } from "kinsun-shared/client";
import { ApiError } from "kinsun-shared/envelope";
import type {
  Appointment,
  CreatedElder,
  Elder,
  HealthReport,
  Medication,
  ReminderItem,
  RiskEventItem,
} from "kinsun-shared/types";

export { ApiError };
export type { Appointment, Elder, Medication, ReminderItem, RiskEventItem };

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

export function listMedications(elderId: string): Promise<Medication[]> {
  return apiFetch(`/api/v1/elders/${elderId}/medications`);
}

export async function addMedication(
  elderId: string,
  name: string,
  slots: string[],
): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/medications`, {
    method: "POST",
    body: JSON.stringify({ name, slots }),
  });
}

export async function updateMedication(
  elderId: string,
  medicationId: string,
  name: string,
  slots: string[],
): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/medications/${medicationId}`, {
    method: "PUT",
    body: JSON.stringify({ name, slots }),
  });
}

export async function deleteMedication(elderId: string, medicationId: string): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/medications/${medicationId}`, { method: "DELETE" });
}

export function listAppointments(elderId: string): Promise<Appointment[]> {
  return apiFetch(`/api/v1/elders/${elderId}/appointments`);
}

export async function addAppointment(
  elderId: string,
  date: string,
  label: string,
  time: string,
): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/appointments`, {
    method: "POST",
    body: JSON.stringify({ date, label, time }),
  });
}

export async function updateAppointment(
  elderId: string,
  appointmentId: string,
  date: string,
  label: string,
  time: string,
): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/appointments/${appointmentId}`, {
    method: "PUT",
    body: JSON.stringify({ date, label, time }),
  });
}

export async function deleteAppointment(elderId: string, appointmentId: string): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/appointments/${appointmentId}`, { method: "DELETE" });
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
