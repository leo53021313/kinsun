"""觀測領域模型：各階段專表的資料列與後台查詢的聚合結果。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebhookEvent:
    webhook_event_id: str
    trace_id: str
    line_user_id: str
    event_type: str
    message_type: str
    payload: dict
    created_at: float


@dataclass(frozen=True)
class AsrCall:
    asr_call_id: str
    trace_id: str
    line_user_id: str
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
    line_user_id: str
    status: str
    latency_ms: int
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    content: str
    error_message: str
    created_at: float


@dataclass(frozen=True)
class TtsCall:
    tts_call_id: str
    trace_id: str
    line_user_id: str
    status: str
    latency_ms: int
    content: str
    error_message: str
    created_at: float


@dataclass(frozen=True)
class Reply:
    reply_id: str
    trace_id: str
    line_user_id: str
    kind: str  # "voice" | "text"
    status: str
    latency_ms: int
    audio_url: str
    created_at: float


@dataclass(frozen=True)
class TraceRiskEvent:
    tier: int
    reason: str
    created_at: float


@dataclass(frozen=True)
class Trace:
    """單輪處理鏈路：webhook → ASR → LLM（可多筆）→ TTS → 回覆＋掛上的風險事件。"""

    trace_id: str
    line_user_id: str
    webhook_event: WebhookEvent | None
    asr_call: AsrCall | None
    llm_calls: list[LlmCall]
    tts_call: TtsCall | None
    reply: Reply | None
    risk_events: list[TraceRiskEvent]
    elder_name: str = ""  # 經 channel_bindings 解析的長輩姓名；查無時空字串


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


@dataclass(frozen=True)
class StageStats:
    stage: str  # "asr" | "llm" | "tts"
    call_count: int
    error_count: int
    avg_latency_ms: float
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
