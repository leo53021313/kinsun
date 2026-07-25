"""觀測領域模型：各階段專表的資料列與後台查詢的聚合結果。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebhookEvent:
    webhook_event_id: str
    trace_id: str
    external_id: str
    channel: str
    event_type: str
    message_type: str
    payload: dict
    created_at: float


@dataclass(frozen=True)
class AsrCall:
    asr_call_id: str
    trace_id: str
    external_id: str
    channel: str
    status: str  # "ok" | "error"
    latency_ms: int
    transcript: str
    source_audio_url: str
    error_message: str
    created_at: float


@dataclass(frozen=True)
class LlmCall:
    llm_call_id: str
    trace_id: str
    external_id: str
    channel: str
    status: str
    latency_ms: int
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    content: str
    error_message: str
    created_at: float
    kind: str = ""  # 見 LLM_CALL_KIND_*；空字串＝加欄前的舊資料，不歸入任何一類


@dataclass(frozen=True)
class RagCall:
    rag_call_id: str
    trace_id: str
    elder_id: str
    query: str
    index_version: str
    status: str
    latency_ms: int
    safety_level: str
    reason: str
    hits: list[dict]
    citations: list[dict]
    created_at: float


@dataclass(frozen=True)
class TtsCall:
    tts_call_id: str
    trace_id: str
    external_id: str
    channel: str
    status: str
    latency_ms: int
    content: str
    error_message: str
    created_at: float


@dataclass(frozen=True)
class Reply:
    reply_id: str
    trace_id: str
    external_id: str
    channel: str
    kind: str  # "voice" | "text"
    status: str
    latency_ms: int
    # 端到端往返（通道收件 → 回覆送達，✅ D-05 戊-2）；NULL＝該輪未量測。
    round_trip_ms: int | None
    audio_url: str
    created_at: float
    # 對應的 Opik trace id（工程觀測開啟時填；供後台深連結直達 Opik）。空＝未啟用/未捕捉。
    opik_trace_id: str = ""


@dataclass(frozen=True)
class TraceRiskEvent:
    tier: int
    reason: str
    created_at: float


@dataclass(frozen=True)
class Trace:
    """單輪處理鏈路：webhook → ASR → LLM（可多筆）→ TTS → 回覆＋掛上的風險事件。"""

    trace_id: str
    external_id: str
    channel: str
    webhook_event: WebhookEvent | None
    asr_call: AsrCall | None
    llm_calls: list[LlmCall]
    rag_calls: list[RagCall]
    tts_call: TtsCall | None
    reply: Reply | None
    risk_events: list[TraceRiskEvent]
    elder_name: str = ""  # 經 channel_bindings 解析的長輩姓名；查無時空字串
    # 對應的 Opik trace id（由 reply 帶出）；供後台深連結直達 Opik，空＝無。
    opik_trace_id: str = ""


@dataclass(frozen=True)
class FeedItem:
    """全域訊息流的一筆：kind ∈ turn／reminder／risk。"""

    kind: str
    elder_id: str
    elder_name: str
    role: str  # turn 專用（user／assistant），其餘為空字串
    content: str
    tier: int | None  # risk 專用
    trace_id: str | None  # risk 專用（可能為 NULL）
    created_at: float


@dataclass(frozen=True)
class TimelineItem:
    """長輩時間軸的一筆：kind ∈ turn／reminder／risk／voice（語音鏈路卡）。"""

    kind: str
    role: str
    content: str
    tier: int | None
    trace_id: str | None
    audio_url: str
    created_at: float


@dataclass(frozen=True)
class ElderActivity:
    elder_id: str
    name: str
    bound_channels: str  # 已綁定通道（逗號串接，如 "line"）；空字串＝未綁定
    last_active_at: float | None


# llm_calls.kind：一輪對話會產生多筆 LLM 呼叫，種類不同、快慢差一個量級
# （審核與分級是短輸入的結構化判斷，回覆生成含工具迴圈）。不分種類就做 p50／p95
# 等於把三種東西平均在一起——2026-07-25 加入濫用審核後，多灌進來的快呼叫會把
# llm 階段的 p50 **拉低**，讓「每輪其實變慢了」在後台顯示成「LLM 變快了」，
# 方向相反的誤導。model_name 無法事後區分：GEMINI_MODEL 與 GEMINI_MODEL_SAFETY
# 預設同值，三種呼叫在表裡長得一模一樣。
LLM_CALL_KIND_AGENT = "agent"  # CareAgent 生成回覆（含工具迴圈）
LLM_CALL_KIND_RISK_CLASSIFY = "risk_classify"  # 危急分級
LLM_CALL_KIND_MODERATION = "moderation"  # 濫用審核
# 統計輸出時的排列順序；空字串（舊資料）另歸 "llm:unknown"，僅在有資料時出現。
LLM_CALL_KINDS = (
    LLM_CALL_KIND_AGENT,
    LLM_CALL_KIND_RISK_CLASSIFY,
    LLM_CALL_KIND_MODERATION,
)


@dataclass(frozen=True)
class StageStats:
    stage: str  # "asr" | "llm:<kind>" | "tts" | "round_trip"
    call_count: int
    error_count: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float


@dataclass(frozen=True)
class HourlyCount:
    hour_start: float
    turn_count: int


@dataclass(frozen=True)
class OverviewStats:
    turn_count: int
    risk_event_count: int
    active_elder_count: int
    llm_input_tokens: int
    llm_output_tokens: int
    stages: list[StageStats]
    hourly_turns: list[HourlyCount]
