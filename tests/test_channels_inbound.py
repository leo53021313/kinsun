from types import SimpleNamespace

from kinsun import turn_context
from kinsun.accounts.models import Channel
from kinsun.channels.inbound import (
    BIND_FIRST_PROMPT,
    FALLBACK_PROMPT,
    NON_AUDIO_PROMPT,
    InboundMessage,
    VoiceReplyDelivery,
    dispatch,
)
from kinsun.llm import LLMError
from kinsun.speech.asr import ASRError
from kinsun.speech.tts import TtsResult
from tests.fakes import FakeTraceStore


class _Replies:
    def __init__(self):
        self.sent = []

    def __call__(self, text):
        self.sent.append(text)


class _Pipeline:
    def __init__(self, text="管線回覆", boom=None):
        self._text = text
        self._boom = boom
        self.calls = []
        self.text_calls = []
        self.obs_marks = []  # (external_id, channel) 觀測標記——庚-07 驗通道有貫穿

    def process(self, audio, *, elder_id, external_id="", channel="", trace_id="", audio_url=""):
        self.calls.append((audio, elder_id))
        self.obs_marks.append((external_id, channel))
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(text=self._text)

    def process_text(self, text, *, elder_id, external_id="", channel="", trace_id=""):
        self.text_calls.append((text, elder_id))
        self.obs_marks.append((external_id, channel))
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(text=self._text)


class _Binding:
    def __init__(self, reply):
        self._reply = reply
        self.calls = []

    def handle(self, line_user_id, text):
        self.calls.append((line_user_id, text))
        return self._reply


class _Gate:
    """resolve_elder 測試替身：allow=True 時把 line id 映到固定 elder id。"""

    def __init__(self, allow):
        self._allow = allow
        self.resolve_calls = 0

    def resolve_elder(self, channel, external_id):
        self.resolve_calls += 1
        return "e-1" if self._allow else None


class _VoicePipeline:
    def __init__(self, result):
        self._result = result

    def process(self, audio, *, elder_id, external_id="", channel="", trace_id="", audio_url=""):
        return self._result


class _SpyVoice:
    def __init__(self):
        self.delivered = []

    def deliver(self, msg, result):
        self.delivered.append((msg.external_id, result.text))


def _msg(kind, *, reply, text="", audio=b"", external_id="U-1", reply_audio=None):
    return InboundMessage(
        Channel.LINE, external_id, kind, text, audio, reply, reply_audio=reply_audio
    )


def test_text_routes_to_binding():
    r = _Replies()
    binding = _Binding("已建立")
    dispatch(
        _msg("text", text="設定", reply=r),
        pipeline=_Pipeline(),
        binding=binding,
        gate=_Gate(True),
    )
    assert binding.calls == [("U-1", "設定")]
    assert r.sent == ["已建立"]


def test_text_default_runs_pipeline():
    """✅ D-11（甲-4）：文字輸入預設走完整對話管線。"""
    r = _Replies()
    pipe = _Pipeline(text="回覆")
    dispatch(
        _msg("text", text="閒聊", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert pipe.text_calls == [("閒聊", "e-1")]
    assert r.sent == ["回覆"]


def test_pipeline_receives_external_id_and_channel_for_observability():
    """✅ 庚-07（A-8）：來源通道與外部識別碼一路帶進管線供觀測五表標記。"""
    pipe = _Pipeline(text="回覆")
    dispatch(
        _msg("text", text="閒聊", reply=_Replies(), external_id="U-9"),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert pipe.obs_marks == [("U-9", "line")]  # channel 取自 InboundMessage.channel


def test_dispatch_skips_resolve_when_elder_id_provided():
    """✅ 庚-12（A-11）：呼叫端（App turns）已解析過本人時傳入 elder_id，
    dispatch 不再重查閘門——省掉每輪一趟重複 DB 往返。"""
    gate = _Gate(True)
    pipe = _Pipeline(text="回覆")
    dispatch(
        _msg("audio", audio=b"\x01", reply=_Replies()),
        pipeline=pipe,
        binding=_Binding(None),
        gate=gate,
        elder_id="e-pre",
    )
    assert gate.resolve_calls == 0
    assert pipe.calls == [(b"\x01", "e-pre")]


def test_dispatch_resolves_when_elder_id_not_provided():
    gate = _Gate(True)
    pipe = _Pipeline(text="回覆")
    dispatch(
        _msg("audio", audio=b"\x01", reply=_Replies()),
        pipeline=pipe,
        binding=_Binding(None),
        gate=gate,
    )
    assert gate.resolve_calls == 1
    assert pipe.calls == [(b"\x01", "e-1")]


def test_text_flag_off_falls_back_to_prompt():
    """關閉旗標＝維運逃生口：回到只收語音的提示。"""
    r = _Replies()
    dispatch(
        _msg("text", text="閒聊", reply=r),
        pipeline=_Pipeline(),
        binding=_Binding(None),
        gate=_Gate(True),
        text_input_enabled=False,
    )
    assert r.sent == [NON_AUDIO_PROMPT]


def test_other_kind_replies_prompt():
    r = _Replies()
    dispatch(_msg("other", reply=r), pipeline=_Pipeline(), binding=_Binding(None), gate=_Gate(True))
    assert r.sent == [NON_AUDIO_PROMPT]


def test_text_flag_on_runs_pipeline():
    r = _Replies()
    pipe = _Pipeline(text="你說的是：哈囉")
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert pipe.text_calls == [("哈囉", "e-1")]
    assert r.sent == ["你說的是：哈囉"]


def test_text_flag_on_binding_command_still_routes_to_binding():
    r = _Replies()
    binding = _Binding("已建立")
    pipe = _Pipeline()
    dispatch(
        _msg("text", text="設定", reply=r),
        pipeline=pipe,
        binding=binding,
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert binding.calls == [("U-1", "設定")]
    assert r.sent == ["已建立"]
    assert pipe.text_calls == []


def test_text_flag_on_blocked_when_gate_denies():
    r = _Replies()
    pipe = _Pipeline()
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(False),
        text_input_enabled=True,
    )
    assert r.sent == [BIND_FIRST_PROMPT]
    assert pipe.text_calls == []


def test_text_flag_on_pipeline_error_replies_fallback():
    r = _Replies()
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=_Pipeline(boom=LLMError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert r.sent == [FALLBACK_PROMPT]


def test_audio_blocked_when_gate_denies():
    r = _Replies()
    pipe = _Pipeline()
    dispatch(
        _msg("audio", audio=b"x", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(False),
    )
    assert r.sent == [BIND_FIRST_PROMPT]
    assert pipe.calls == []


def test_audio_runs_pipeline_when_allowed():
    r = _Replies()
    pipe = _Pipeline(text="你說的是：早安")
    dispatch(
        _msg("audio", audio=b"xy", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert pipe.calls == [(b"xy", "e-1")]
    assert r.sent == ["你說的是：早安"]


def test_audio_pipeline_error_replies_fallback():
    r = _Replies()
    dispatch(
        _msg("audio", audio=b"x", reply=r),
        pipeline=_Pipeline(boom=ASRError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert r.sent == [FALLBACK_PROMPT]


def test_dispatch_declares_inline_delivery_when_reply_audio_present():
    """有 reply_audio（WS 通道）→ 宣告內嵌投遞；沒有（LINE／POST）→ 不宣告。"""
    seen: list[bool] = []

    class _Probe:
        def process(self, audio, **kwargs):
            seen.append(turn_context.is_inline_audio_delivery())
            return TtsResult(text="回覆", audio=b"x", duration_ms=1)

    dispatch(
        _msg("audio", audio=b"a", reply=_Replies(), reply_audio=lambda *a: None),
        pipeline=_Probe(),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=_SpyVoice(),
    )
    assert seen == [True]

    seen.clear()
    dispatch(
        _msg("audio", audio=b"a", reply=_Replies()),
        pipeline=_Probe(),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=_SpyVoice(),
    )
    assert seen == [False]


class _VoiceCapture:
    def __init__(self):
        self.text_sent = []
        self.voice_sent = []

    def reply(self, text):
        self.text_sent.append(text)

    def reply_voice(self, url, duration_ms, text):
        self.voice_sent.append((url, duration_ms, text))


class _Publisher:
    def __init__(self, url="http://x/a.m4a", boom=False):
        self._url = url
        self._boom = boom

    def publish(self, audio, *, content_type):
        if self._boom:
            from kinsun.audio.publisher import AudioPublishError

            raise AudioPublishError("boom")
        return self._url


def _voice_msg(cap):
    return InboundMessage(Channel.LINE, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice)


def test_deliver_text_when_no_audio():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=True).deliver(
        _voice_msg(cap), TtsResult(text="純文字", audio=None)
    )
    assert cap.text_sent == ["純文字"]
    assert cap.voice_sent == []


def test_deliver_voice_with_text():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=True).deliver(
        _voice_msg(cap), TtsResult(text="嗨", audio=b"A", duration_ms=800)
    )
    assert cap.voice_sent == [("http://x/a.m4a", 800, "嗨")]
    assert cap.text_sent == []


def test_deliver_voice_without_text_when_disabled():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=False).deliver(
        _voice_msg(cap), TtsResult(text="嗨", audio=b"A", duration_ms=800)
    )
    assert cap.voice_sent == [("http://x/a.m4a", 800, None)]


def test_deliver_falls_back_to_text_on_publish_error():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(boom=True), include_text=True).deliver(
        _voice_msg(cap), TtsResult(text="退化文字", audio=b"A", duration_ms=800)
    )
    assert cap.text_sent == ["退化文字"]
    assert cap.voice_sent == []


def test_deliver_text_when_publisher_none():
    cap = _VoiceCapture()
    VoiceReplyDelivery(None, include_text=True).deliver(
        _voice_msg(cap), TtsResult(text="泡泡", audio=None)
    )
    assert cap.text_sent == ["泡泡"]


def test_audio_success_routes_to_voice_when_present():
    voice = _SpyVoice()
    dispatch(
        _msg("audio", audio=b"x", reply=_Replies()),
        pipeline=_VoicePipeline(TtsResult(text="語音回覆", audio=b"A", duration_ms=100)),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=voice,
    )
    assert voice.delivered == [("U-1", "語音回覆")]


def test_deliver_shows_transcript_when_enabled():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=True, show_transcript=True).deliver(
        _voice_msg(cap),
        TtsResult(text="好喔", audio=b"A", duration_ms=100, transcript="今天天氣真好"),
    )
    assert cap.voice_sent == [("http://x/a.m4a", 100, "辨識：今天天氣真好\n\n回復：好喔")]


def test_deliver_no_transcript_when_disabled():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=True, show_transcript=False).deliver(
        _voice_msg(cap),
        TtsResult(text="好喔", audio=b"A", duration_ms=100, transcript="今天天氣真好"),
    )
    assert cap.voice_sent == [("http://x/a.m4a", 100, "好喔")]


def test_dispatch_records_voice_reply():
    traces = FakeTraceStore()
    cap = _VoiceCapture()
    msg = InboundMessage(
        Channel.LINE,
        "U-1",
        "audio",
        "",
        b"xy",
        cap.reply,
        cap.reply_voice,
        trace_id="t1",
        audio_url="https://x/in.m4a",
    )
    result = TtsResult(text="回覆", audio=b"\x00", duration_ms=800)
    voice = VoiceReplyDelivery(_Publisher(url="https://x/out.m4a"), include_text=True)
    dispatch(
        msg,
        pipeline=_VoicePipeline(result),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=voice,
        traces=traces,
        timer=iter([0.0, 0.2]).__next__,
    )
    assert len(traces.replies) == 1
    assert traces.replies[0].trace_id == "t1"
    assert traces.replies[0].kind == "voice"
    assert traces.replies[0].audio_url == "https://x/out.m4a"
    assert traces.replies[0].latency_ms == 200


def test_dispatch_records_text_reply_when_no_voice():
    traces = FakeTraceStore()
    r = _Replies()
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", r, trace_id="t2")
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="純文字")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
        timer=iter([0.0, 0.1]).__next__,
    )
    assert traces.replies[0].kind == "text"
    assert traces.replies[0].audio_url == ""


def test_dispatch_stores_opik_trace_id_on_reply(monkeypatch):
    """care_conversation trace context 內抓到的 Opik trace id 隨 reply 落庫（供後台深連結）。"""
    from kinsun import tracing

    monkeypatch.setattr(tracing, "current_opik_trace_id", lambda: "opik-999")
    traces = FakeTraceStore()
    r = _Replies()
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", r, trace_id="t9")
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="嗨")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
        timer=iter([0.0, 0.1]).__next__,
    )
    assert traces.replies[0].opik_trace_id == "opik-999"


def test_dispatch_without_trace_id_records_nothing():
    traces = FakeTraceStore()
    r = _Replies()
    dispatch(
        _msg("audio", audio=b"x", reply=r),
        pipeline=_VoicePipeline(TtsResult(text="hi")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
    )
    assert traces.replies == []  # 無 trace_id（非觀測路徑）不記


def test_dispatch_records_round_trip_from_received_at():
    """✅ D-05（戊-2）：received_at（通道收件時刻）→ 回覆送達的端到端往返延遲落庫。"""
    traces = FakeTraceStore()
    r = _Replies()
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", r, trace_id="t3", received_at=0.5)
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="回覆")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
        timer=iter([1.0, 1.25]).__next__,
    )
    assert traces.replies[0].latency_ms == 250  # 發送段：1.0 → 1.25
    assert traces.replies[0].round_trip_ms == 750  # 端到端：0.5 → 1.25


def test_dispatch_round_trip_null_when_received_at_unknown():
    traces = FakeTraceStore()
    r = _Replies()
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", r, trace_id="t4")
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="回覆")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
        timer=iter([0.0, 0.1]).__next__,
    )
    assert traces.replies[0].round_trip_ms is None


class _ChunkedPipeline:
    """回傳已分段結果的管線替身，用來驗 dispatch 交出去的 outcome。"""

    def __init__(self, reply: str, chunk_count: int, transcript: str = "") -> None:
        self._result = TtsResult(
            text=reply, audio=b"A", duration_ms=900, transcript=transcript, chunk_count=chunk_count
        )

    def process(self, audio, **kwargs):
        return self._result

    def process_text(self, text, **kwargs):
        return self._result


def test_dispatch_reports_chunk_count_and_digest_of_the_real_reply():
    """digest 必須由**真正的回覆文字**算出，不是投遞層的顯示字串。

    ⚠️ 這條是實機驗證踩出來的（2026-07-26）：`ASR_DEBUG_SHOW_TRANSCRIPT=true` 時，
    文字泡泡會變成「辨識：…\\n\\n回復：…」，而分段端點是從 `turns` 讀**純回覆**重新
    切句比對。兩邊來源不同，雜湊就永遠對不上——每一段都被判為過期、回 409，長輩只
    聽得到第一句。單元測試若只驗「有沒有 digest」不會發現，故這裡把來源釘死。
    """
    from kinsun.speech.chunking import reply_digest

    reply = "阿公今天早上好嗎。今天天氣不錯，要不要出去走走？"
    cap = _VoiceCapture()
    msg = InboundMessage(
        Channel.APP, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice, received_at=1.0
    )

    outcome = dispatch(
        msg,
        pipeline=_ChunkedPipeline(reply, chunk_count=2, transcript="醫生說我血壓有點高"),
        binding=_Binding(None),
        gate=None,
        voice=VoiceReplyDelivery(_Publisher(), include_text=True, show_transcript=True),
        elder_id="e1",
    )

    assert outcome.chunk_count == 2
    assert outcome.reply_digest == reply_digest(reply)
    # 續段要切的那串文字同理（2026-08-01 審查 Critical 1）：`ws.py` 拿它去
    # `split_for_speech`，餵成顯示字串的話第一句會被當成續段再唸一次。
    assert outcome.reply_text == reply
    # 顯示字串確實帶了 debug 前綴——證明本測試真的踩在那個分岔上。
    assert cap.voice_sent[0][2].startswith("辨識：")


def test_unchunked_reply_carries_no_digest():
    """沒分段就不該給 digest——前端據此判斷「不必再拉後續段落」。"""
    cap = _VoiceCapture()
    msg = InboundMessage(Channel.APP, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice)

    outcome = dispatch(
        msg,
        pipeline=_ChunkedPipeline("就這一句話而已喔阿公", chunk_count=0),
        binding=_Binding(None),
        gate=None,
        voice=VoiceReplyDelivery(_Publisher(), include_text=True),
        elder_id="e1",
    )

    assert outcome.chunk_count == 0
    assert outcome.reply_digest == ""


# ── 回退話術也要有聲音（V-02，2026-07-29）────────────────────────────────
#
# 管線失敗時原本只走 msg.reply()＝文字，語音投遞在下一行、永遠到不了。對看不到螢幕
# 的長輩，那一輪就是按下說話鍵、等五秒、然後完全沒有反應——跟斷線一模一樣。
# 回退話術在啟動時就預錄好（standby_phrases），這裡只查表送出，不合成、不上傳。


def _standby(url="http://x/standby.m4a", duration_ms=1500):
    from kinsun.speech.ack_audio import AckClip

    return lambda text: AckClip(text=text, audio_url=url, duration_ms=duration_ms)


def test_pipeline_failure_speaks_the_fallback_instead_of_only_texting_it():
    cap = _VoiceCapture()
    dispatch(
        InboundMessage(Channel.APP, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice),
        pipeline=_Pipeline(boom=LLMError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=VoiceReplyDelivery(_Publisher(), include_text=True, standby_clip=_standby()),
    )
    assert cap.voice_sent == [("http://x/standby.m4a", 1500, FALLBACK_PROMPT)]
    assert cap.text_sent == []


def test_pipeline_failure_falls_back_to_text_when_no_standby_clip_is_warm():
    """還沒暖好／簽章過期＝沒有音檔，退回文字。降級不是錯誤，不可讓這輪沒有回覆。"""
    cap = _VoiceCapture()
    dispatch(
        InboundMessage(Channel.APP, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice),
        pipeline=_Pipeline(boom=ASRError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=VoiceReplyDelivery(_Publisher(), include_text=True, standby_clip=lambda text: None),
    )
    assert cap.text_sent == [FALLBACK_PROMPT]
    assert cap.voice_sent == []


def test_pipeline_failure_falls_back_to_text_when_channel_has_no_voice_handle():
    """LINE 這類沒有 reply_voice 的通道照舊送文字。"""
    r = _Replies()
    dispatch(
        _msg("audio", audio=b"x", reply=r),
        pipeline=_Pipeline(boom=ASRError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=VoiceReplyDelivery(_Publisher(), include_text=True, standby_clip=_standby()),
    )
    assert r.sent == [FALLBACK_PROMPT]


def test_standby_voice_send_failure_still_delivers_text():
    """送語音那一步自己炸掉時仍要有文字——回退話術本身不能再失敗一次。"""
    cap = _VoiceCapture()

    def _boom(url, duration_ms, text):
        raise RuntimeError("送不出去")

    msg = InboundMessage(Channel.APP, "U-1", "audio", "", b"x", cap.reply, _boom)
    dispatch(
        msg,
        pipeline=_Pipeline(boom=LLMError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=VoiceReplyDelivery(_Publisher(), include_text=True, standby_clip=_standby()),
    )
    assert cap.text_sent == [FALLBACK_PROMPT]


def test_standby_lookup_failure_still_delivers_text():
    """查表本身炸掉（不該發生，但它在對話路徑上）也不可讓長輩什麼都沒收到。"""
    cap = _VoiceCapture()

    def _boom(text):
        raise RuntimeError("查表壞了")

    dispatch(
        InboundMessage(Channel.APP, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice),
        pipeline=_Pipeline(boom=LLMError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=VoiceReplyDelivery(_Publisher(), include_text=True, standby_clip=_boom),
    )
    assert cap.text_sent == [FALLBACK_PROMPT]
    assert cap.voice_sent == []


def test_pipeline_failure_without_voice_still_texts_the_fallback():
    """沒有語音投遞層（純文字後端／本機開發）時的既有行為不變。"""
    r = _Replies()
    dispatch(
        _msg("audio", audio=b"x", reply=r),
        pipeline=_Pipeline(boom=ASRError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert r.sent == [FALLBACK_PROMPT]


# ── 端到端秒數要進得了 Opik（2026-08-08 觀測盤點）──
#
# `round_trip_ms` 原本只寫進 Postgres 的 `replies`，Opik 一個字都沒有——想看端到端
# 分布只能查 DB，而 Opik 上那個 trace 時長比它短（trace 根在容量閘門之後才開始）。
# `log_feedback_score` 早就定義好、也匯出了，全庫零呼叫。


def _spy_trace_writes(monkeypatch):
    """攔下 update_current_trace，看 metadata 與 feedback score 有沒有寫上去。

    ⚠️ `opik.track` 也必須換成 identity：只開 `_ENABLED` 而不換掉它，`@tracing.track`
    會真的去初始化 Opik client 連 localhost:5273——單元測試不可以連任何東西。
    而且 `tracing.track` 的包裝是**首次呼叫時**建好就快取的，一旦讓真的那個進了快取，
    同一個 pytest 行程裡之後的每一個測試都會跟著連線。
    """
    import opik

    from kinsun.tracing import client as tracing_client
    from kinsun.tracing import decorators as tracing_decorators

    calls: list[dict] = []
    monkeypatch.setattr(opik, "track", lambda **kw: lambda f: f)
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)
    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(opik.opik_context, "update_current_trace", lambda **kw: calls.append(kw))
    return calls


def test_dispatch_sends_round_trip_to_opik(monkeypatch):
    calls = _spy_trace_writes(monkeypatch)
    msg = InboundMessage(
        Channel.LINE, "U-1", "audio", "", b"xy", _Replies(), trace_id="t9", received_at=0.5
    )
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="回覆")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=FakeTraceStore(),
        timer=iter([1.0, 1.25]).__next__,
    )
    scores = [s for c in calls for s in c.get("feedback_scores", [])]
    assert {"name": "round_trip_ms", "value": 750, "reason": ""} in scores


def test_dispatch_skips_the_opik_score_when_round_trip_is_unknown(monkeypatch):
    """起點未知時不可掛 0——0 毫秒的往返會直接毀掉整條分布的可信度。"""
    calls = _spy_trace_writes(monkeypatch)
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", _Replies(), trace_id="t10")
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="回覆")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=FakeTraceStore(),
        timer=iter([0.0, 0.1]).__next__,
    )
    scores = [s for c in calls for s in c.get("feedback_scores", [])]
    assert [s for s in scores if s["name"] == "round_trip_ms"] == []


def test_dispatch_records_admission_wait_on_the_trace(monkeypatch):
    """排隊等待只能是 metadata：它發生在 trace 根開始之前，沒有 span 容得下。"""
    from kinsun import turn_context

    calls = _spy_trace_writes(monkeypatch)
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", _Replies(), trace_id="t11")
    with turn_context.admission_wait(4321):
        dispatch(
            msg,
            pipeline=_VoicePipeline(TtsResult(text="回覆")),
            binding=_Binding(None),
            gate=_Gate(True),
            traces=FakeTraceStore(),
            timer=iter([0.0, 0.1]).__next__,
        )
    metadata = [c.get("metadata", {}) for c in calls]
    assert any(m.get("admission_wait_ms") == 4321 for m in metadata)
