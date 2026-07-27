/**
 * 觀測後台 API 呼叫端（乙-5）：/api/v1/admin＋統一信封解包；型別來自 kinsun-shared 共用包。
 * 認證：X-Admin-Key 共用金鑰（401 即清除，App 殼層導回輸入頁）。
 */

import { createApiClient } from "kinsun-shared/client";
import { ApiError } from "kinsun-shared/envelope";
import type {
  AdminElder,
  AdminElderAccount,
  AdminElderMemory,
  AdminElderReminders,
  AdminJob,
  AdminJobsMeta,
  AdminNewsItem,
  AdminRiskNotification,
  FeedMessage,
  HourlyCount,
  Meta,
  Overview,
  OverviewAlert,
  RagStatus,
  StageStats,
  Timeline,
  TimelineItem,
  TraceDetail,
} from "kinsun-shared/types";

export { ApiError };
export type {
  AdminElder,
  AdminElderAccount,
  AdminElderMemory,
  AdminElderReminders,
  AdminJob,
  AdminJobsMeta,
  AdminNewsItem,
  AdminRiskNotification,
  FeedMessage,
  HourlyCount,
  Meta,
  Overview,
  OverviewAlert,
  RagStatus,
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

// 共同流程住共用包（✅ 庚-30）；admin 差異＝X-Admin-Key＋401 時清金鑰通知殼層。
const client = createApiClient({
  authHeaders: () => {
    const headers: Record<string, string> = {};
    const key = getAdminKey();
    if (key) {
      headers["X-Admin-Key"] = key;
    }
    return headers;
  },
  onUnauthorized: () => {
    clearAdminKey();
    onUnauthorized?.();
  },
});

const apiFetch = client.requestWithMeta;

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

// --- 內測基礎建設（spec 2026-07-12）：長輩詳情分頁＋排程觀測與手動觸發 ---

/** 公開 meta：內測模式（手動觸發按鈕顯示與否）。 */
export async function getMeta(): Promise<Meta> {
  return (await apiFetch<Meta>("/api/v1/meta")).data;
}

export async function getElderReminders(elderId: string): Promise<AdminElderReminders> {
  return (await apiFetch<AdminElderReminders>(`/api/v1/admin/elders/${elderId}/reminders`)).data;
}

export async function getElderMemory(elderId: string): Promise<AdminElderMemory> {
  return (await apiFetch<AdminElderMemory>(`/api/v1/admin/elders/${elderId}/memory`)).data;
}

export async function getElderAccount(elderId: string): Promise<AdminElderAccount> {
  return (await apiFetch<AdminElderAccount>(`/api/v1/admin/elders/${elderId}/account`)).data;
}

export async function listElderRiskNotifications(
  elderId: string,
): Promise<AdminRiskNotification[]> {
  return (
    await apiFetch<AdminRiskNotification[]>(`/api/v1/admin/elders/${elderId}/risk-notifications`)
  ).data;
}

/**
 * 排程狀態＋逾期告警。
 *
 * ⚠️ 一併回傳 meta（不只 data）：`warnings` 是後端算好的人話告警，前端不再自己
 * 推導一次。2026-07-26 排程停擺 13 天，後台這一頁只印了 `last_run_at`——資料
 * 明明就在畫面上，卻沒有人（也沒有任何顏色）說它不對勁。
 */
export async function listJobs(): Promise<{ jobs: AdminJob[]; meta: AdminJobsMeta }> {
  const res = await apiFetch<AdminJob[]>("/api/v1/admin/jobs");
  const meta = (res.meta ?? {}) as Partial<AdminJobsMeta>;
  return {
    jobs: res.data,
    meta: {
      overdue: meta.overdue ?? [],
      never_ran: meta.never_ran ?? [],
      warnings: meta.warnings ?? [],
    },
  };
}

export async function getRagStatus(): Promise<RagStatus> {
  return (await apiFetch<RagStatus>("/api/v1/admin/rag/status")).data;
}

/** 話題新聞檢視（D-74 消費端）：看爬蟲近況。 */
export async function listNews(days = 3): Promise<AdminNewsItem[]> {
  return (await apiFetch<AdminNewsItem[]>(`/api/v1/admin/news?days=${days}`)).data;
}

/** 內測限定：立即執行排程任務。 */
export async function runJob(jobName: string): Promise<void> {
  await apiFetch(`/api/v1/admin/jobs/${jobName}/run`, { method: "POST" });
}

/** 內測限定：立即發送某長輩的用藥／回診提醒。 */
export async function dispatchReminder(
  elderId: string,
  body: { kind: "medication" | "appointment" | "custom" },
): Promise<void> {
  await apiFetch(`/api/v1/admin/elders/${elderId}/reminders/dispatch`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
