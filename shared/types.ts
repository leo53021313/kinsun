/** 三端共用的 API 資源型別（✅ D-51，乙-5）：與後端 JSON 鍵名完全一致（snake_case）。 */

// --- 家屬面資源 ---
export type Elder = { elder_id: string; name: string };
export type CreatedElder = Elder & { invite_code: string };
/** 統一排程（D-76 P3）：用藥、回診與長輩自訂提醒共用同一個資源。 */
export type ScheduleKind = "medication" | "appointment" | "custom";
export type RepeatKind = "once" | "daily" | "weekly";
/** 一個鬧鐘。重複型帶 time（＋weekly 的 weekday）；一次性帶 scheduled_at。 */
export type ScheduleOccurrence = {
  schedule_id: string;
  repeat: RepeatKind;
  time: string;
  weekday: number | null;
  scheduled_at: number | null;
};
/** 一件事：同一個 group 的全部鬧鐘。UI 一律以此為單位。 */
export type ScheduleGroup = {
  group_id: string;
  kind: ScheduleKind;
  title: string;
  /** elder＝長輩自己用說的建的；guardian＝家屬設的。 */
  created_by: "elder" | "guardian";
  /** 事件本身的時刻（回診看診時間）；null＝與提醒時刻相同。 */
  event_at: number | null;
  occurrences: ScheduleOccurrence[];
};
/** 建立／修改排程的請求內容。 */
export type ScheduleInput = {
  kind: ScheduleKind;
  title: string;
  occurrences: { repeat: RepeatKind; time?: string; date?: string; weekday?: number | null }[];
  event_date?: string;
  event_time?: string;
};
export type RiskEventItem = { tier: number; reason: string; created_at: number };
export type ReminderItem = { kind: string; content: string; created_at: number };
export type HealthReport = { risk_events: RiskEventItem[]; reminders: ReminderItem[] };
export type DailySummary = { date: string; content: string; created_at: number };
export type AppNotification = { content: string; created_at: number };

// --- App 認證 ---
export type GuardianSession = { guardian_id: string; name: string; token: string };
export type ElderSession = { elder_id: string; name: string; token: string };
export type TurnReply = {
  text: string;
  audio_url: string;
  /** 回覆音檔時長；目前三端零消費，保留給虛擬形象動畫對嘴（階段 5 後）。 */
  duration_ms: number | null;
  /**
   * 分段串流（2026-07-26 延遲優化）：整段回覆被切成幾段。
   * >1 代表 `audio_url` 只是**第一段**，其餘要用 `getTurnChunk` 依序取來接著播；
   * 0／1 代表就這一段。TTS 是 0.9 秒固定成本＋每字 0.10 秒，整段合成完才送出
   * 會讓長輩等 5～8 秒，先送第一句可提早約 2～4 秒聽到聲音。
   */
  chunk_count: number;
  /** 這一輪回覆的短雜湊；取後續段落時帶上，伺服器據此確認不是上一輪的回覆。 */
  reply_digest: string;
};

/** 分段串流的後續段落（第 0 段已隨 `TurnReply` 回過）。 */
export type TurnChunk = {
  audio_url: string;
  duration_ms: number | null;
  text: string;
};

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
export type TraceRagCall = {
  query: string;
  index_version: string;
  status: string;
  latency_ms: number;
  safety_level: string;
  reason: string;
  hits: {
    chunk_id: string;
    source_id: string;
    score: number;
    retrieval_method: string;
  }[];
  citations: {
    source_id: string;
    title: string;
    publisher: string;
    url: string;
    chunk_id: string;
  }[];
  created_at: number;
};
export type TraceDetail = {
  trace_id: string;
  external_id: string;
  channel: string;
  elder_name: string;
  webhook_event: TraceWebhookEvent | null;
  asr_call: TraceAsrCall | null;
  llm_calls: TraceLlmCall[];
  rag_calls: TraceRagCall[];
  tts_call: TraceTtsCall | null;
  reply: TraceReply | null;
  risk_events: TraceRiskEvent[];
  // 直達對應 Opik trace 的深連結；工程觀測開啟且捕捉到 id 時才有，否則空字串（前端隱藏連結）。
  opik_url: string;
};

// --- 觀測後台：長輩詳情分頁（spec 2026-07-12） ---
/** 後台提醒分頁的單筆鬧鐘（D-76 P5：三類合成一份清單，kind 保留分類）。 */
export type AdminSchedule = {
  schedule_id: string;
  group_id: string;
  kind: ScheduleKind;
  title: string;
  repeat: RepeatKind;
  time: string;
  weekday: number | null;
  scheduled_at: number | null;
  event_at: number | null;
  created_by: "elder" | "guardian";
};
export type AdminReminderLog = { kind: string; content: string; created_at: number };
export type AdminElderReminders = {
  schedules: AdminSchedule[];
  reminder_logs: AdminReminderLog[];
};
export type AdminMemoryItem = { text: string; provenance: string; date: string };
export type AdminSummaryItem = { date: string; content: string; created_at: number };
export type AdminElderMemory = { memories: AdminMemoryItem[]; summaries: AdminSummaryItem[] };
export type AdminBinding = { channel: string; external_id: string; created_at: number };
export type AdminInvite = {
  code: string;
  role: string;
  status: string;
  expires_at: number;
  attempts: number;
};
export type AdminConsent = {
  consent_by: string;
  version: string;
  granted_at: number;
  revoked_at: number | null;
};
export type AdminGuardianLink = {
  guardian_id: string;
  name: string;
  role: string;
  escalation_order: number;
};
export type AdminElderAccount = {
  bindings: AdminBinding[];
  invites: AdminInvite[];
  consent: AdminConsent | null;
  has_password_account: boolean;
  phone: string | null;
  tokens: { created_at: number }[];
  guardians: AdminGuardianLink[];
};
export type AdminRiskNotification = {
  guardian_id: string;
  guardian_name: string;
  tier: number;
  delivered: boolean;
  /** 實際走的通道（逗號串接如 "line,app"；空＝無可達通道或舊資料）。 */
  channels: string;
  created_at: number;
};
export type AdminJob = {
  job_name: string;
  cron: string;
  last_run_at: number | null;
  /** 依 cron 算出的下次應執行時刻；`null` ＝ 從未執行過，無基準可算。 */
  due_at: number | null;
  /** 遲到秒數；未逾期一律 0。 */
  late_seconds: number;
  /** 已逾期未執行——排程器可能停擺或認領不到工作。 */
  is_overdue: boolean;
  /** 從未執行過。⚠️ 與 is_overdue 互斥：沒有基準就談不上逾期，但更不該當成健康。 */
  never_ran: boolean;
};
/** `GET /admin/jobs` 的 meta：逾期與從未執行分列，另附人話告警。 */
export type AdminJobsMeta = {
  overdue: string[];
  never_ran: string[];
  warnings: string[];
};
export type RagStatus = {
  active_release: string | null;
  active_published_at: number | null;
  latest_release: string | null;
  latest_status: string | null;
  latest_completed_at: number | null;
  document_count: number;
  chunk_count: number;
  content_policy: "allowed_only" | "classroom_demo";
  warnings: string[];
};

// --- 公開 meta（spec 2026-07-12 內測基礎建設） ---
export type Meta = { internal_testing: boolean };

// --- 話題新聞檢視（D-74 消費端，admin 觀測） ---
export type AdminNewsItem = {
  news_item_id: string;
  source_id: string;
  title: string;
  url: string;
  publisher: string;
  published_at: number | null;
  retrieved_at: number;
};
