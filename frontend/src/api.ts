/**
 * LIFF 端 API 呼叫端（乙-5）：/api/v1＋統一信封解包；型別與錯誤來自 kinsun-shared 共用包。
 * 認證：LIFF idToken（隨 LINE 凍結，退場時移除，ADR-009）。
 */

import liff from "@line/liff";

import { ApiError, type Envelope, unwrapEnvelope } from "kinsun-shared/envelope";
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

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = liff.getIDToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  if (res.status === 204) return undefined as T;
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, `http_${res.status}`);
  }
  return unwrapEnvelope(res.status, body);
}

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
): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/appointments`, {
    method: "POST",
    body: JSON.stringify({ date, label }),
  });
}

export async function updateAppointment(
  elderId: string,
  appointmentId: string,
  date: string,
  label: string,
): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/appointments/${appointmentId}`, {
    method: "PUT",
    body: JSON.stringify({ date, label }),
  });
}

export async function deleteAppointment(elderId: string, appointmentId: string): Promise<void> {
  await apiFetch(`/api/v1/elders/${elderId}/appointments/${appointmentId}`, { method: "DELETE" });
}

export function createElder(elderName: string, guardianName: string): Promise<CreatedElder> {
  return apiFetch("/api/v1/elders", {
    method: "POST",
    body: JSON.stringify({ name: elderName, guardian_name: guardianName }),
  });
}

export function generateGuardianInvite(elderId: string): Promise<{ invite_code: string }> {
  return apiFetch(`/api/v1/elders/${elderId}/guardian-invites`, { method: "POST" });
}

export function getHealthReport(elderId: string): Promise<HealthReport> {
  return apiFetch(`/api/v1/elders/${elderId}/health-report`);
}
