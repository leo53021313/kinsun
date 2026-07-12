/**
 * 觀測後台 API 呼叫端（乙-5）：/api/v1/admin＋統一信封解包；型別來自 kinsun-shared 共用包。
 * 認證：X-Admin-Key 共用金鑰（401 即清除，App 殼層導回輸入頁）。
 */

import { ApiError, type Envelope, unwrapEnvelope } from "kinsun-shared/envelope";
import type {
  AdminElder,
  FeedMessage,
  HourlyCount,
  Overview,
  OverviewAlert,
  StageStats,
  Timeline,
  TimelineItem,
  TraceDetail,
} from "kinsun-shared/types";

export { ApiError };
export type {
  AdminElder,
  FeedMessage,
  HourlyCount,
  Overview,
  OverviewAlert,
  StageStats,
  Timeline,
  TimelineItem,
  TraceDetail,
};

const KEY_STORAGE = "kinsun-admin-key";

export function getAdminKey(): string | null {
  return localStorage.getItem(KEY_STORAGE);
}

export function setAdminKey(key: string): void {
  localStorage.setItem(KEY_STORAGE, key);
}

export function clearAdminKey(): void {
  localStorage.removeItem(KEY_STORAGE);
}

// 401 通知（✅ D-52 丁-7）：金鑰失效時讓 App 殼層切回輸入頁，不必手動重整。
let onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(callback: (() => void) | null): void {
  onUnauthorized = callback;
}

async function apiFetch<T>(path: string): Promise<{ data: T; meta: Record<string, unknown> | null }> {
  const headers = new Headers();
  const key = getAdminKey();
  if (key) headers.set("X-Admin-Key", key);
  const res = await fetch(path, { headers });
  if (res.status === 401) {
    clearAdminKey();
    onUnauthorized?.();
  }
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, `http_${res.status}`);
  }
  return { data: unwrapEnvelope(res.status, body), meta: body.meta };
}

export async function getOverview(): Promise<Overview> {
  return (await apiFetch<Overview>("/api/v1/admin/overview")).data;
}

export async function listMessages(after: number, limit = 100): Promise<FeedMessage[]> {
  const res = await apiFetch<FeedMessage[]>(`/api/v1/admin/messages?after=${after}&limit=${limit}`);
  return res.data;
}

/** 回翻歷史（✅ D-29 乙-6）：取比 before 更舊的訊息；hasMore 由信封 meta 提供。 */
export async function listMessagesBefore(
  before: number,
  limit = 100,
): Promise<{ messages: FeedMessage[]; hasMore: boolean }> {
  const res = await apiFetch<FeedMessage[]>(
    `/api/v1/admin/messages?before=${before}&limit=${limit}`,
  );
  return { messages: res.data, hasMore: Boolean(res.meta?.has_more) };
}

export async function listElders(): Promise<AdminElder[]> {
  return (await apiFetch<AdminElder[]>("/api/v1/admin/elders")).data;
}

export async function getTimeline(elderId: string, date: string): Promise<Timeline> {
  const query = date ? `?date=${date}` : "";
  return (await apiFetch<Timeline>(`/api/v1/admin/elders/${elderId}/timeline${query}`)).data;
}

export async function getTrace(traceId: string): Promise<TraceDetail> {
  return (await apiFetch<TraceDetail>(`/api/v1/admin/traces/${traceId}`)).data;
}
