/** 三端共用的 API 資源型別（✅ D-51，乙-5）：與後端 JSON 鍵名完全一致（snake_case）。 */

// --- 家屬面資源 ---
export type Elder = { elder_id: string; name: string };
export type CreatedElder = Elder & { invite_code: string };
export type Medication = { medication_id: string; name: string; slots: string[] };
export type Appointment = { appointment_id: string; date: string; label: string };
export type RiskEventItem = { tier: number; reason: string; created_at: number };
export type ReminderItem = { kind: string; content: string; created_at: number };
export type HealthReport = { risk_events: RiskEventItem[]; reminders: ReminderItem[] };
export type AppNotification = { content: string; created_at: number };

// --- App 認證 ---
export type GuardianSession = { guardian_id: string; name: string; token: string };
export type ElderSession = { elder_id: string; name: string; token: string };
export type TurnReply = { text: string; audio_url: string; duration_ms: number | null };

// --- 觀測後台（admin） ---
export type StageStats = {
  stage: string;
  call_count: number;
  error_count: number;
  avg_latency_ms: number;
  p50_latency_ms: number;
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
export type Timeline = { elder_id: string; name: string; date: string; items: TimelineItem[] };
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
  round_trip_ms: number | null;
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
