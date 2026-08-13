"""通道中立的入站訊息與分派（不依賴任何特定通道 SDK）。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from kinsun import tracing, turn_context
from kinsun.accounts.models import Channel
from kinsun.agent import SYSTEM_TROUBLE_REPLY
from kinsun.llm import LLMError
from kinsun.memory.shortterm import MemoryStoreError
from kinsun.observability.store import TraceStore, safe_record
from kinsun.speech.ack_audio import AckClip
from kinsun.speech.asr import ASRError
from kinsun.speech.chunking import reply_digest
from kinsun.speech.tts import TtsResult

logger = logging.getLogger("kinsun.inbound")

# 人稱與 agent 層的 SYSTEM_PROMPT 同一套（2026-08-07 新視覺人設）：角色叫阿白、
# 對長輩說話一律第一人稱「我」；「金孫」只留作服務名。原文「金孫現在聽得懂語音喔，
# 您可以按住麥克風跟我說說話」在同一句裡先第三人稱自稱金孫、再第一人稱說「跟我
# 說」，對長輩而言那是兩個不同的對象。
NON_AUDIO_PROMPT = "我現在聽得懂語音喔，您可以按住麥克風跟我說說話。"
# 回退話術與 agent 層共用單一出處（✅ 庚-37）。這裡走的是**系統故障**那一句：
# 觸發點是 ASRError／LLMError／MemoryStoreError，也就是服務出錯，不是長輩講不清楚
# ——叫他再說一次只會讓他一再重試、一再失敗（2026-07-26 實測 M4）。
FALLBACK_PROMPT = SYSTEM_TROUBLE_REPLY
BIND_FIRST_PROMPT = (
    "要先完成綁定，我才能陪您聊天喔。請把家人給您的邀請碼貼到這裡，或回覆「設定」開始。"
)


@dataclass(frozen=True)
class InboundMessage:
    """通道中立的入站訊息。kind ∈ text/audio/other；reply 為綁定好的回覆 handle，
    reply_voice 為語音回覆 handle（url、duration_ms、text）。
    channel＋external_id 為來源通道與其帳號識別（如 LINE userId），分派時解析成本人。
    trace_id／audio_url 供觀測鏈路與音檔回放（無觀測時為空字串）。
    received_at 為通道收件時刻的單調時鐘值（與 dispatch 的 timer 同源，✅ D-05 戊-2
    往返延遲起點）；0＝未知，該輪 round_trip_ms 記 NULL。

    reply_audio（2026-07-30 延遲優化 C1）＝**把音檔本體直接交回通道**的 handle
    （audio bytes、duration_ms、text、chunk_count、reply_digest）。有它的通道
    （App 的 WebSocket）不必等「上傳 Supabase→簽章→App 再下載」那兩趟網路；
    None＝照舊走 `reply_voice`（LINE 只收得到訊息裡的音檔 URL，`POST /turns` 是
    單次請求／回應、沒有推播通道）。"""

    channel: Channel
    external_id: str
    kind: str
    text: str
    audio: bytes
    reply: Callable[[str], None]
    reply_voice: Callable[[str, int, str | None], None] | None = None
    trace_id: str = ""
    audio_url: str = ""
    received_at: float = 0.0
    reply_audio: Callable[[bytes, int, str | None, int, str], None] | None = None


@dataclass(frozen=True)
class DeliveryOutcome:
    """回覆實際送出的形式：voice（含公開音檔 URL）或 text。"""

    kind: str
    audio_url: str = ""
    # 分段串流（2026-07-26 延遲優化）：>1 代表送出的只是第一段，呼叫端（App 對講機）
    # 據此告訴前端還有幾段要拉。LINE 收不到分段（只能一則語音），故恆為 0。
    chunk_count: int = 0
    # 這一輪回覆的短雜湊，前端取後續段落時帶上。⚠️ 由**真正的回覆文字**算出，不是
    # 投遞層的顯示字串——後者在 debug 模式會多「辨識：…」前綴，與 turns 的內容不同。
    reply_digest: str = ""
    # 這一輪**真正的回覆文字**（`TtsResult.text`），給「投遞之後還要拿它做事」的呼叫端
    # 用——目前只有 `ws.py::_push_continuation_chunks`（續段逐段合成）。
    #
    # ⚠️ **不是投遞層的顯示字串**（與 `reply_digest` 同一條紀律，理由也同一個）：
    # `show_transcript` 為真時顯示字串是「辨識：…\n\n回復：…」，拿它去
    # `split_for_speech` 切出來的段落與 `pipeline._synthesize` 切的**不是同一組**
    # ——第一段變成「辨識：…」、原本的第一句於是被當成續段再唸一次（2026-08-01
    # 全分支審查 Critical 1，`speech/chunking.py::reply_digest` 早在 2026-07-26
    # 就把同一個坑寫成明文警告）。
    #
    # 與 `chunk_count` 住同一個物件是刻意的：一個說「我宣告了幾段」，一個說
    # 「那幾段是從哪串文字切出來的」，兩者必須同源，分開放遲早會分岔。
    reply_text: str = ""


def chunk_info(result) -> tuple[int, str]:
    """本輪的分段資訊：(段數, 回覆短雜湊)；未分段回 (0, "")。

    ⚠️ 單一出處（2026-07-30 C1）：`_run_pipeline` 與 `VoiceReplyDelivery._deliver_inline`
    都要這兩個值，各算一次遲早會分岔成「送出的段數」與「宣告的段數」不一致，App 就會
    多播或漏播一段。`getattr` 預設 0 的理由見 `_run_pipeline`（produce 是通道中立的
    seam，測試替身只保證有 text／audio）。

    雜湊由**真正的回覆文字**算出，不是投遞層的顯示字串——後者在 debug 模式會多
    「辨識：…」前綴，與 `turns` 表裡的內容不同，續拉就會對不上而永遠 409。
    """
    count = getattr(result, "chunk_count", 0)
    return (count, reply_digest(result.text) if count > 1 else "")


class VoiceReplyDelivery:
    """把 TtsResult 發成回覆（通道中立，✅ 庚-37）：有音檔→上傳→語音（可附文字）；
    否則→文字泡泡。
    上傳或語音回覆失敗一律退回文字，絕不讓回覆消失。
    show_transcript：debug 用，在文字泡泡最前面附上本輪 ASR 辨識到的長者原話
    （只進文字泡泡、不進語音合成）。"""

    def __init__(
        self,
        publisher,
        include_text: bool,
        show_transcript: bool = False,
        *,
        standby_clip: Callable[[str], AckClip | None] | None = None,
    ) -> None:
        self._publisher = publisher
        self._include_text = include_text
        self._show_transcript = show_transcript
        self._standby_clip = standby_clip

    def _compose_text(self, result: TtsResult, *, include_reply: bool) -> str | None:
        # debug 模式：「辨識：…」空一行「回復：…」；非 debug 就只回覆文字。
        if self._show_transcript and result.transcript:
            parts = [f"辨識：{result.transcript}"]
            if include_reply:
                parts.append(f"回復：{result.text}")
            return "\n\n".join(parts)
        return result.text if include_reply else None

    @tracing.track(name="deliver", type="general", capture_input=False, capture_output=False)
    def deliver(self, msg: InboundMessage, result: TtsResult) -> DeliveryOutcome:
        if result.audio is None:
            msg.reply(self._compose_text(result, include_reply=True) or result.text)
            return DeliveryOutcome(kind="text")
        if msg.reply_audio is not None:
            return self._deliver_inline(msg, result)
        if self._publisher is None or msg.reply_voice is None:
            msg.reply(self._compose_text(result, include_reply=True) or result.text)
            return DeliveryOutcome(kind="text")
        try:
            url = self._publisher.publish(result.audio, content_type="audio/mp4")
            text = self._compose_text(result, include_reply=self._include_text)
            msg.reply_voice(url, result.duration_ms, text)
            return DeliveryOutcome(kind="voice", audio_url=url)
        except Exception:  # noqa: BLE001 - 任何失敗都退回文字
            logger.warning("語音回覆失敗，退回文字泡泡")
            msg.reply(self._compose_text(result, include_reply=True) or result.text)
            return DeliveryOutcome(kind="text")

    def _deliver_inline(self, msg: InboundMessage, result: TtsResult) -> DeliveryOutcome:
        """音檔本體直接交回通道，之後才上傳存證（2026-07-30 延遲優化 C1）。

        ⚠️ **順序就是這一刀的全部價值**：原本的路是「上傳 Supabase→取簽章→App 拿到
        URL→App 再向 Supabase 下載」，音檔在網路上走兩趟、長輩要等完第一趟才聽得到。
        先把 bytes 推下去，長輩立刻有聲音；上傳留在後面純為存證（`replies.audio_url`
        是後台回放的依據），此時已經沒有人在等它。

        上傳失敗只留 warning、**不退回文字**：音檔已經送到長輩耳朵裡了，這一輪對他來說
        完全成功，只是後台少一筆可回放的錄音。這與 `deliver` 那條路的「上傳失敗退文字」
        是不同情境——那裡上傳失敗等於長輩什麼都拿不到。

        推送失敗（連線斷了）才退回文字：與 `deliver` 同一條紀律，回覆絕不消失。
        """
        chunk_count, digest = chunk_info(result)
        text = self._compose_text(result, include_reply=self._include_text)
        try:
            msg.reply_audio(result.audio, result.duration_ms, text, chunk_count, digest)
        except Exception:  # noqa: BLE001 - 推不出去就退回文字，回覆不可消失
            logger.warning("語音回覆（內嵌音檔）失敗，退回文字泡泡")
            msg.reply(self._compose_text(result, include_reply=True) or result.text)
            return DeliveryOutcome(kind="text")
        url = ""
        if self._publisher is not None:
            try:
                url = self._publisher.publish(result.audio, content_type="audio/mp4")
            except Exception:  # noqa: BLE001 - 存證失敗不影響長輩（他已經聽到了）
                logger.warning("回覆音檔存證上傳失敗（長輩已收到音檔，後台將無回放）")
        return DeliveryOutcome(kind="voice", audio_url=url)

    def deliver_standby(self, msg: InboundMessage, text: str) -> DeliveryOutcome:
        """回退話術的投遞（V-02，2026-07-29）：用**啟動時預錄好**的音檔送語音。

        為什麼不能沿用 `deliver`：那條路要一個 `TtsResult`，也就是要當場合成——而走到
        這裡代表管線已經失敗（ASR／LLM／記憶其中之一），再花 1.9 秒合成一句「有點小
        狀況」既慢又可能同樣失敗。這裡只查表拿現成的網址。

        取不到音檔就退回文字，與 `deliver` 同一條紀律：回覆絕不消失。對純語音的長輩
        來說，文字≈沒有回應——但「文字」仍然遠好過「什麼都沒有」，後者跟斷線無法區分。
        """
        clip = None
        if self._standby_clip is not None and msg.reply_voice is not None:
            try:
                clip = self._standby_clip(text)
            except Exception:  # noqa: BLE001 - 查表在對話路徑上，壞掉也只是沒有音檔
                logger.warning("待命話術查表失敗，退回文字泡泡")
        if clip is None:
            msg.reply(text)
            return DeliveryOutcome(kind="text")
        try:
            msg.reply_voice(clip.audio_url, clip.duration_ms, text)
            return DeliveryOutcome(kind="voice", audio_url=clip.audio_url)
        except Exception:  # noqa: BLE001 - 送不出語音就送文字
            logger.warning("待命話術語音回覆失敗，退回文字泡泡")
            msg.reply(text)
            return DeliveryOutcome(kind="text")


def dispatch(
    msg: InboundMessage,
    *,
    pipeline,
    binding,
    gate,
    voice=None,
    traces: TraceStore | None = None,
    text_input_enabled: bool = True,
    timer: Callable[[], float] = time.monotonic,
    elder_id: str | None = None,
) -> DeliveryOutcome | None:
    """elder_id：呼叫端已解析過本人時傳入（✅ 庚-12），dispatch 不再重查閘門；
    未傳（LINE webhook 路徑）照舊經 gate 解析。"""
    if msg.kind == "text":
        reply = binding.handle(msg.external_id, msg.text)
        if reply is not None:
            msg.reply(reply)
            return None
        # 非綁定自由文字走完整對話管線（危急偵測＋回覆＋記憶，✅ D-11 與語音同等對待）；
        # 旗標關為維運逃生口，回到只收語音提示。
        if not text_input_enabled:
            msg.reply(NON_AUDIO_PROMPT)
            return None
        elder_id = elder_id or gate.resolve_elder(msg.channel, msg.external_id)
        if elder_id is None:
            msg.reply(BIND_FIRST_PROMPT)
            return None
        with turn_context.inline_audio_delivery(msg.reply_audio is not None):
            return _run_pipeline(
                msg,
                lambda: pipeline.process_text(
                    msg.text,
                    elder_id=elder_id,
                    external_id=msg.external_id,
                    channel=msg.channel.value,
                    trace_id=msg.trace_id,
                ),
                voice=voice,
                traces=traces,
                timer=timer,
            )
    if msg.kind != "audio":
        msg.reply(NON_AUDIO_PROMPT)
        return None
    elder_id = elder_id or gate.resolve_elder(msg.channel, msg.external_id)
    if elder_id is None:
        msg.reply(BIND_FIRST_PROMPT)
        return None
    with turn_context.inline_audio_delivery(msg.reply_audio is not None):
        return _run_pipeline(
            msg,
            lambda: pipeline.process(
                msg.audio,
                elder_id=elder_id,
                external_id=msg.external_id,
                channel=msg.channel.value,
                trace_id=msg.trace_id,
                audio_url=msg.audio_url,
            ),
            voice=voice,
            traces=traces,
            timer=timer,
        )


@tracing.track(name="care_conversation", type="general", capture_input=False, capture_output=False)
def _run_pipeline(
    msg: InboundMessage,
    produce: Callable[[], TtsResult],
    *,
    voice,
    traces: TraceStore | None,
    timer: Callable[[], float],
) -> None:
    """執行對話管線並發送回覆：語音與文字共用。任一階段失敗回退提示。

    這是一次對話的 Opik trace root（工程視角）：內含 pipeline 各階段 span 與投遞 span，
    kinsun trace_id／elder_id 由 pipeline 內的 tag_current_trace 掛上（含 thread 分組）。
    """
    # 排隊等待只能以 metadata 進 trace，不能是 span：容量閘門包住的是本函式，排隊
    # 整段發生在這個 root 開始之前（見 `turn_context.admission_wait` 的說明）。
    # 0 也照寫——「這輪沒有排隊」與「這欄位沒人填」是兩件事，後者查起來會卡住。
    tracing.update_trace_metadata(admission_wait_ms=turn_context.current_admission_wait_ms())
    try:
        result = produce()
    except (ASRError, LLMError, MemoryStoreError) as exc:
        logger.warning("對話管線失敗（回退提示）：%s: %s", type(exc).__name__, exc)
        # ⚠️ 這裡走 deliver_standby 而不是 msg.reply（V-02，2026-07-29）：原本直接回文字
        # 就 return，語音投遞在下面永遠到不了，所以就算 TTS 完全健康，回退話術也一律
        # 無聲。對看不到螢幕的長輩，那一輪＝按下說話鍵、等五秒、什麼都沒有，跟斷線
        # 分不出來（實測 p7：「伊有時陣攏無聲，干焦有字，我毋知伊有咧應無」）。
        if voice is not None:
            voice.deliver_standby(msg, FALLBACK_PROMPT)
        else:
            msg.reply(FALLBACK_PROMPT)
        return None
    started = timer()
    if voice is not None:
        # 「or」容忍測試替身回 None（既有 _SpyVoice 類 fake）。
        outcome = voice.deliver(msg, result) or DeliveryOutcome(kind="text")
    else:
        msg.reply(result.text)
        outcome = DeliveryOutcome(kind="text")
    # 段數與雜湊走 `chunk_info` 單一出處（見其 docstring）：投遞層的內嵌音檔路徑
    # 也要同一組值，兩邊各算一次遲早會分岔。
    # `reply_text` 一併在這裡填：它與段數必須來自**同一個** `result.text`，呼叫端
    # 才不會拿到「宣告 3 段、但那 3 段是從另一串文字切出來的」（見 DeliveryOutcome）。
    chunk_count, digest = chunk_info(result)
    outcome = replace(outcome, chunk_count=chunk_count, reply_digest=digest, reply_text=result.text)
    _record_reply(traces, msg, outcome, started, timer)
    return outcome


def _record_reply(
    traces: TraceStore | None,
    msg: InboundMessage,
    outcome: DeliveryOutcome,
    started: float,
    timer: Callable[[], float],
) -> None:
    ended = timer()
    latency_ms = int((ended - started) * 1000)
    # 往返延遲（✅ D-05 戊-2）：通道收件 → 回覆送達的端到端耗時；起點未知記 NULL。
    round_trip_ms = int((ended - msg.received_at) * 1000) if msg.received_at else None
    # ⚠️ 掛在 trace 上而不是只落庫（2026-08-08 觀測盤點）：這個數字原本只在 Postgres
    # 的 `replies` 裡，Opik 一個字都沒有——想看端到端分布只能查 DB，而 Opik 上那個
    # trace 時長**比它短**（trace 根在容量閘門之後才開始，實測差 246ms 中位）。用
    # feedback score 而非 metadata，是因為只有前者在 Opik 上聚合得起來（要看的是
    # p50／p95，不是單筆）。
    # ⚠️ 起點未知時整個略過，不可補 0：一筆 0 毫秒的往返會直接毀掉整條分布。
    # 這幾行刻意排在 `traces is None` 的守門**之前**——Opik 與 Postgres 是兩套獨立
    # 的觀測，沒有理由讓其中一套的缺席連帶關掉另一套。
    if round_trip_ms is not None:
        tracing.log_feedback_score("round_trip_ms", round_trip_ms)
    if traces is None or not msg.trace_id:
        return
    # 在 care_conversation trace context 內抓 Opik trace id 存下，供後台深連結（停用回空字串）。
    opik_trace_id = tracing.current_opik_trace_id()
    safe_record(
        lambda: traces.record_reply(
            trace_id=msg.trace_id,
            external_id=msg.external_id,
            channel=msg.channel.value,
            kind=outcome.kind,
            status="ok",
            latency_ms=latency_ms,
            round_trip_ms=round_trip_ms,
            audio_url=outcome.audio_url,
            opik_trace_id=opik_trace_id,
        )
    )
