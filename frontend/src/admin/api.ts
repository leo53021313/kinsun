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

export class ApiError extends Error {
  constructor(public status: number) {
    super(`API ${status}`);
  }
}

async function apiFetch(path: string): Promise<Response> {
  const headers = new Headers();
  const key = getAdminKey();
  if (key) headers.set("X-Admin-Key", key);
  const res = await fetch(path, { headers });
  if (res.status === 401) clearAdminKey();
  if (!res.ok) throw new ApiError(res.status);
  return res;
}

export type StageStats = {
  stage: string;
  call_count: number;
  error_count: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
};

export type HourlyCount = { hour_start: number; turn_count: number };

export type OverviewAlert = { kind: string; count: number; window_minutes: number };

export type Overview = {
  generated_at: number;
  turn_count: number;
  risk_event_count: number;
  active_elder_count: number;
  llm_input_tokens: number;
  llm_output_tokens: number;
  stages: StageStats[];
  hourly_turns: HourlyCount[];
  alerts: OverviewAlert[];
};

export type FeedMessage = {
  kind: string;
  elder_id: string;
  elder_name: string;
  role: string;
  content: string;
  tier: number | null;
  trace_id: string | null;
  created_at: number;
};

export type AdminElder = {
  elder_id: string;
  name: string;
  bound_channels: string;
  last_active_at: number | null;
};

export type TimelineItem = {
  kind: string;
  role: string;
  content: string;
  tier: number | null;
  trace_id: string | null;
  audio_url: string;
  created_at: number;
};

export type Timeline = {
  elder_id: string;
  name: string;
  date: string;
  items: TimelineItem[];
};

export type TraceWebhookEvent = {
  event_type: string;
  message_type: string;
  payload: Record<string, unknown>;
  created_at: number;
};

export type TraceAsrCall = {
  status: string;
  latency_ms: number;
  transcript: string;
  source_audio_url: string;
  error_message: string;
  created_at: number;
};

export type TraceLlmCall = {
  status: string;
  latency_ms: number;
  model_name: string;
  input_tokens: number | null;
  output_tokens: number | null;
  content: string;
  error_message: string;
  created_at: number;
};

export type TraceTtsCall = {
  status: string;
  latency_ms: number;
  content: string;
  error_message: string;
  created_at: number;
};

export type TraceReply = {
  kind: string;
  status: string;
  latency_ms: number;
  audio_url: string;
  created_at: number;
};

export type TraceRiskEvent = { tier: number; reason: string; created_at: number };

export type TraceDetail = {
  trace_id: string;
  line_user_id: string;
  elder_name: string;
  webhook_event: TraceWebhookEvent | null;
  asr_call: TraceAsrCall | null;
  llm_calls: TraceLlmCall[];
  tts_call: TraceTtsCall | null;
  reply: TraceReply | null;
  risk_events: TraceRiskEvent[];
};

export async function getOverview(): Promise<Overview> {
  const res = await apiFetch("/api/admin/overview");
  return (await res.json()) as Overview;
}

export async function listMessages(after: number, limit = 100): Promise<FeedMessage[]> {
  const res = await apiFetch(`/api/admin/messages?after=${after}&limit=${limit}`);
  return ((await res.json()) as { messages: FeedMessage[] }).messages;
}

export async function listElders(): Promise<AdminElder[]> {
  const res = await apiFetch("/api/admin/elders");
  return ((await res.json()) as { elders: AdminElder[] }).elders;
}

export async function getTimeline(elderId: string, date: string): Promise<Timeline> {
  const query = date ? `?date=${date}` : "";
  const res = await apiFetch(`/api/admin/elders/${elderId}/timeline${query}`);
  return (await res.json()) as Timeline;
}

export async function getTrace(traceId: string): Promise<TraceDetail> {
  const res = await apiFetch(`/api/admin/traces/${traceId}`);
  return (await res.json()) as TraceDetail;
}
