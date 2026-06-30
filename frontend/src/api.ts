import liff from "@line/liff";

export type Elder = { elder_id: string; name: string };
export type Medication = { med_id: string; name: string; slots: string[] };

export class ApiError extends Error {
  constructor(public status: number) {
    super(`API ${status}`);
  }
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = liff.getIDToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) throw new ApiError(res.status);
  return res;
}

export async function listElders(): Promise<Elder[]> {
  const res = await apiFetch("/api/me/elders");
  return ((await res.json()) as { elders: Elder[] }).elders;
}

export async function listMedications(elderId: string): Promise<Medication[]> {
  const res = await apiFetch(`/api/elders/${elderId}/medications`);
  return ((await res.json()) as { medications: Medication[] }).medications;
}

export async function addMedication(
  elderId: string,
  name: string,
  slots: string[],
): Promise<void> {
  await apiFetch(`/api/elders/${elderId}/medications`, {
    method: "POST",
    body: JSON.stringify({ name, slots }),
  });
}

export async function updateMedication(
  elderId: string,
  medId: string,
  name: string,
  slots: string[],
): Promise<void> {
  await apiFetch(`/api/elders/${elderId}/medications/${medId}`, {
    method: "PUT",
    body: JSON.stringify({ name, slots }),
  });
}

export async function deleteMedication(elderId: string, medId: string): Promise<void> {
  await apiFetch(`/api/elders/${elderId}/medications/${medId}`, { method: "DELETE" });
}

export type Appointment = { appt_id: string; date: string; label: string };

export async function listAppointments(elderId: string): Promise<Appointment[]> {
  const res = await apiFetch(`/api/elders/${elderId}/appointments`);
  return ((await res.json()) as { appointments: Appointment[] }).appointments;
}

export async function addAppointment(
  elderId: string,
  date: string,
  label: string,
): Promise<void> {
  await apiFetch(`/api/elders/${elderId}/appointments`, {
    method: "POST",
    body: JSON.stringify({ date, label }),
  });
}

export async function updateAppointment(
  elderId: string,
  apptId: string,
  date: string,
  label: string,
): Promise<void> {
  await apiFetch(`/api/elders/${elderId}/appointments/${apptId}`, {
    method: "PUT",
    body: JSON.stringify({ date, label }),
  });
}

export async function deleteAppointment(elderId: string, apptId: string): Promise<void> {
  await apiFetch(`/api/elders/${elderId}/appointments/${apptId}`, { method: "DELETE" });
}

export async function createElder(
  elderName: string,
  guardianName: string,
): Promise<{ elder_id: string; name: string; invite_code: string }> {
  const res = await apiFetch("/api/elders", {
    method: "POST",
    body: JSON.stringify({ elder_name: elderName, guardian_name: guardianName }),
  });
  return (await res.json()) as { elder_id: string; name: string; invite_code: string };
}

export async function generateGuardianInvite(
  elderId: string,
): Promise<{ invite_code: string }> {
  const res = await apiFetch(`/api/elders/${elderId}/guardian-invites`, { method: "POST" });
  return (await res.json()) as { invite_code: string };
}
