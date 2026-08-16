/** 三端共用的 API 資源型別（✅ D-51，乙-5）：與後端 JSON 鍵名完全一致（snake_case）。 */

// --- 家屬面資源 ---
/** nickname＝金孫對長輩的稱謂（如「秀英阿嬤」），空字串＝未設定。
 *  ⚠️ 後端 `GET /elders` 與 `POST /elders` 一直都有回這個欄位，型別卻沒宣告
 *  （A-10，2026-07-29）：TS 消費端因此**取不到**一個明明送過來的值，而編譯器不會
 *  提醒任何人——它只是安靜地不存在。前後端同鍵名是本檔的存在理由。 */
/** `persona`＝金孫對這位長輩用哪一種語氣（2026-08-05）。值域見後端 `personas.py`。 */
export type Elder = { elder_id: string; name: string; nickname: string; persona: string };
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
/**
 * 通知的呈現分級（2026-08-01 Leo 裁決）：`notice`＝一般提醒／主動關懷，
 * `alert`＝危急警報。字面值與後端 `NotificationSeverity`、資料庫欄位三處完全一致。
 */
export type NotificationSeverity = "notice" | "alert";
/**
 * ⚠️ `severity` 宣告為**選填**是刻意的，不是「還沒補齊」：後端 2026-08-01 起一定
 * 會送，但這個型別同時要描述兩種讀得到舊資料的情形——①後端還沒部署到新版；
 * ②`app/`（已凍結）打的是同一組端點。少了 `?`，前端會以為這個欄位保證存在而
 * 直接拿去比對，實際拿到 `undefined` 時靜默走進錯誤分支。
 *
 * ⚠️ **不要直接把這個值當成兩種樣式的判斷依據**——它可能是 `undefined`，也可能
 * 是未來後端新增、而這一版前端還不認得的值。一律先過
 * `web/src/notify/severity.ts::toBannerSeverity` 收斂。
 */
export type AppNotification = {
  content: string;
  created_at: number;
  severity?: NotificationSeverity;
};

// --- 長輩客製化聲音（家屬錄一段參考語音，2026-08-12 接上前端） ---

/**
 * 家屬錄音前要照唸的稿子與注意事項。
 *
 * ⚠️ **由伺服器下發，前端不得寫死**：這份文字同時是 `voice_profiles.prompt_text`
 * （CosyVoice zero-shot 要「參考音檔＋逐字稿」成對輸入），兩邊各存一份遲早漂移，
 * 而漂移的症狀是合成品質靜默變差、沒有任何錯誤訊息。
 */
export type VoiceProfileScript = {
  script: string;
  tips: string[];
  /** 這份稿子為什麼長這樣；後台／說明用，畫面不一定顯示。 */
  rationale: Record<string, string>;
};

/**
 * 這位長輩目前的客製化聲音狀態。
 *
 * ⚠️ 後端刻意**不回音檔也不回可下載網址**（那是長輩家人的聲音樣本）。因此送出
 * 之後就再也無法聽到錄了什麼——這正是送出前一定要能試聽的原因。
 */
export type VoiceProfileStatus = {
  elder_id: string;
  has_profile: boolean;
  consented_by?: string;
  /** epoch 秒。 */
  granted_at?: number;
};

// --- App 認證 ---
export type GuardianSession = { guardian_id: string; name: string; token: string };
export type ElderSession = { elder_id: string; name: string; token: string };
export type TurnReply = {
  /** ASR 辨識出的長輩原話；只回到長輩自己的裝置，不提供給家屬端清單。 */
  transcript: string;
  text: string;
  audio_url: string;
  /** 回覆音檔時長；Expo App 會與當段文字一起送給阿白 renderer 做 viseme 對嘴。 */
  duration_ms: number | null;
  /**
   * 分段串流（2026-07-26 延遲優化）：整段回覆被切成幾段。
   * ⚠️ 2026-08-01 續段語音 WS 直送之後，這個欄位純粹是**資訊性**的——續段不再
   * 靠前端拿它去請求（`getTurnChunk`／`GET /turns/chunks/{index}` 已移除），
   * 而是由後端在第一段送出後主動用 WS `chunk` binary frame 逐段推送。
   * 0／1 代表就這一段（POST 降級路徑恆為 0，見 D-3：只有 WS 通道會分段）。
   * TTS 是 0.9 秒固定成本＋每字 0.10 秒，整段合成完才送出會讓長輩等 5～8 秒，
   * 先送第一句可提早約 2～4 秒聽到聲音。
   */
  chunk_count: number;
  /** 這一輪回覆的短雜湊；取後續段落時帶上，伺服器據此確認不是上一輪的回覆。 */
  reply_digest: string;
  /**
   * 阿白這一輪臉上的表情（D-82，2026-08-16），由 LLM 隨回覆一起挑。
   *
   * ⚠️ **空字串是正常值**：功能關閉、模型沒給、舊版後端都會是空的。那時角色
   * renderer 會自己從回覆文字判讀情緒（它一直都會），所以呈現層**不可以**把空
   * 字串當成「平靜」送進去——那等於把 renderer 的判讀關掉。
   */
  emotion?: string;
};

/**
 * 分段串流的後續段落（第 0 段已隨 `TurnReply` 回過）。
 *
 * ⚠️ **已於 2026-08-01 隨 WS 續段直送退場**：`web/` 不再使用（改被動接收
 * `chunk` frame），對應的 `GET /api/v1/turns/chunks/{index}` 端點已移除。
 * 仍保留在此僅因**已凍結**（2026-07-30）的 `app/`（`app/src/lib/api.ts::getTurnChunk`
 * ／`app/src/app/elder/talk.tsx`）還在編譯期引用這個型別；App 目前不會被執行，
 * 故這是死引用而非執行期錯誤，但日後若解凍，那兩處呼叫會打到一個已經 404 的端點。
 */
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
  /**
   * 哪個程序負責執行它（字面即 `kinsun.sh` 的服務名，如 `scheduler`、`rag_worker`）。
   * 逾期時該重啟的不一定是排程器——沒有這一欄，值班的人會對著健康的排程器查半天。
   */
  owner: string;
  /** 後台能否就地「立即執行」。跑在別的程序的排程（RAG 週更）為 false。 */
  can_run_now: boolean;
  last_run_at: number | null;
  /** 依 cron 算出的下次應執行時刻；`null` ＝ 從未執行過，無基準可算。 */
  due_at: number | null;
  /** 遲到秒數；未逾期一律 0。 */
  late_seconds: number;
  /** 已逾期未執行——負責的程序可能停擺或認領不到工作。 */
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
