from datetime import datetime, timedelta, timezone

from kinsun.llm import Message
from kinsun.reports.summaries import summarize_day
from tests.fakes import FakeConversationSummaryStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 11, 3, 0, tzinfo=TPE)  # 凌晨 3 點，摘要前一天 7/10


class _ShortTerm:
    def __init__(self, turns):
        self._turns = turns

    def previous_day(self, line_user_id):
        return self._turns


class _StubSummarizer:
    def __init__(self, text="阿公今天聊天氣，心情不錯"):
        self.text = text
        self.calls = []

    def generate(self, *, system_prompt, messages):
        self.calls.append((system_prompt, messages))
        return self.text


def test_summarize_day_writes_summary():
    summaries = FakeConversationSummaryStore()
    turns = [Message("user", "今天天氣真好"), Message("assistant", "是啊")]
    summarize_day(
        "u1",
        short_term=_ShortTerm(turns),
        summarizer=_StubSummarizer(),
        summaries=summaries,
        clock=lambda: NOW,
    )
    rows = summaries.list_for_elder("u1")
    assert len(rows) == 1
    assert rows[0].date == "2026-07-10"
    assert rows[0].content == "阿公今天聊天氣，心情不錯"


def test_summarize_day_writes_summary_to_span_io(monkeypatch):
    """摘要成品攤在 span output（raw LLM I/O 已在 wrap_genai 子 span）。"""
    from kinsun import tracing

    calls: list[dict] = []
    monkeypatch.setattr(tracing, "set_current_span_io", lambda **kw: calls.append(kw))
    turns = [Message("user", "今天天氣真好"), Message("assistant", "是啊")]
    summarize_day(
        "u1",
        short_term=_ShortTerm(turns),
        summarizer=_StubSummarizer(),
        summaries=FakeConversationSummaryStore(),
        clock=lambda: NOW,
    )
    assert calls == [{"span_output": {"summary": "阿公今天聊天氣，心情不錯"}}]


def test_summarize_day_attaches_summary_prompt(monkeypatch):
    """每日摘要把 SUMMARY_PROMPT 註冊/連結到 trace（方案 A）。"""
    from kinsun import tracing
    from kinsun.reports.summaries import SUMMARY_PROMPT

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(tracing, "attach_prompt", lambda n, c: calls.append((n, c)))
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨"), Message("assistant", "好")]),
        summarizer=_StubSummarizer(),
        summaries=FakeConversationSummaryStore(),
        clock=lambda: NOW,
    )
    assert ("daily_summary", SUMMARY_PROMPT) in calls


def test_summarize_day_skips_when_no_turns():
    summaries = FakeConversationSummaryStore()
    summarize_day(
        "u1",
        short_term=_ShortTerm([]),
        summarizer=_StubSummarizer(),
        summaries=summaries,
        clock=lambda: NOW,
    )
    assert summaries.list_for_elder("u1") == []


# --- 摘要生成穩健化（2026-07-17 功能測試發現：39% 空回應、接話、格式污染）---


class _SeqSummarizer:
    """依序回放腳本的替身：元素為字串（回傳值）或例外（拋出）。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def generate(self, *, system_prompt, messages):
        self.calls.append((system_prompt, messages))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def test_summarizer_receives_single_user_transcript():
    """對話以單一 user 文字稿餵入，不再用 user/assistant 歷史（模型會接話）。"""
    summaries = FakeConversationSummaryStore()
    summarizer = _StubSummarizer()
    turns = [Message("user", "今天天氣真好"), Message("assistant", "是啊")]
    summarize_day(
        "u1",
        short_term=_ShortTerm(turns),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
    )
    messages = summarizer.calls[0][1]
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert "長輩：今天天氣真好" in messages[0].content
    assert "金孫：是啊" in messages[0].content


def test_summary_retries_once_on_llm_error():
    from kinsun.llm import LLMError

    summaries = FakeConversationSummaryStore()
    summarizer = _SeqSummarizer([LLMError("Gemini 回應為空"), "長輩今天心情不錯。"])
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
    )
    assert len(summarizer.calls) == 2
    assert summaries.list_for_elder("u1")[0].content == "長輩今天心情不錯。"


def test_summary_raises_after_two_llm_errors():
    import pytest

    from kinsun.llm import LLMError

    summaries = FakeConversationSummaryStore()
    summarizer = _SeqSummarizer([LLMError("Gemini 回應為空"), LLMError("Gemini 回應為空")])
    with pytest.raises(LLMError):
        summarize_day(
            "u1",
            short_term=_ShortTerm([Message("user", "嗨")]),
            summarizer=summarizer,
            summaries=summaries,
            clock=lambda: NOW,
        )
    assert summaries.list_for_elder("u1") == []
    assert len(summarizer.calls) == 2


def test_summary_strips_markdown_and_heading_noise():
    """實測 Gemini 會回「***」分隔線與「**長輩今日狀況摘要：**」標題行，須清掉。"""
    summaries = FakeConversationSummaryStore()
    summarizer = _StubSummarizer("\n***\n\n**長輩今日狀況摘要：**\n長輩今天心情不錯，有出門散步。")
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
    )
    assert summaries.list_for_elder("u1")[0].content == "長輩今天心情不錯，有出門散步。"


def test_summary_strips_html_tags():
    """實測 Gemini 會夾帶 </blockquote> 等 HTML 標籤。"""
    summaries = FakeConversationSummaryStore()
    summarizer = _StubSummarizer("</blockquote>\n長輩今天在家看電視休息。")
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
    )
    assert summaries.list_for_elder("u1")[0].content == "長輩今天在家看電視休息。"


def test_summary_rejects_chat_continuation_and_retries():
    """實測會回「心情有沒有比較好？」這種接話短問句——不是摘要，須重試。"""
    summaries = FakeConversationSummaryStore()
    summarizer = _SeqSummarizer(["心情有沒有比較好？", "長輩今天心情平穩，聊了日常。"])
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
    )
    assert len(summarizer.calls) == 2
    assert summaries.list_for_elder("u1")[0].content == "長輩今天心情平穩，聊了日常。"


def test_summary_rejects_prompt_echo_lines():
    """實測會複述指令（「請提供這段對話的摘要。」）再接正文，複述行須剔除。"""
    summaries = FakeConversationSummaryStore()
    summarizer = _StubSummarizer("請提供這段對話的摘要。\n長輩今天收到鄰居送的芒果，心情愉快。")
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
    )
    assert summaries.list_for_elder("u1")[0].content == "長輩今天收到鄰居送的芒果，心情愉快。"


def test_summary_raises_when_both_attempts_unusable():
    import pytest

    from kinsun.llm import LLMError

    summaries = FakeConversationSummaryStore()
    summarizer = _SeqSummarizer(["心情有沒有比較好？", "那邊還有人在野餐嗎？"])
    with pytest.raises(LLMError):
        summarize_day(
            "u1",
            short_term=_ShortTerm([Message("user", "嗨")]),
            summarizer=summarizer,
            summaries=summaries,
            clock=lambda: NOW,
        )
    assert summaries.list_for_elder("u1") == []


# --- 每日摘要納入 L1 小訊號（✅ D-10 己-5）---


def _l1(reason, ts, *, signals=None):
    from kinsun.safety.tiers import RiskAssessment, RiskTier

    return RiskAssessment(RiskTier.L1, 0.5, reason, signals or ["llm"]), ts


def _events_store(assessments_with_ts):
    from tests.fakes import FakeRiskEventStore

    ts_iter = iter([ts for _, ts in assessments_with_ts])
    store = FakeRiskEventStore(clock=lambda: next(ts_iter))
    for assessment, _ in assessments_with_ts:
        store.record("u1", assessment)
    return store


def _day_ts(hour):
    return datetime(2026, 7, 10, hour, 0, tzinfo=TPE).timestamp()


def test_summary_prompt_includes_yesterdays_l1_signals():
    summaries = FakeConversationSummaryStore()
    summarizer = _StubSummarizer()
    events = _events_store([_l1("最近睡不好", _day_ts(10)), _l1("胃口不佳", _day_ts(15))])
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
        risk_events=events,
    )
    system_prompt = summarizer.calls[0][0]
    assert "最近睡不好" in system_prompt
    assert "胃口不佳" in system_prompt


def test_summary_ignores_l2_failsafe_and_out_of_day_events():
    from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskAssessment, RiskTier

    summaries = FakeConversationSummaryStore()
    summarizer = _StubSummarizer()
    events = _events_store(
        [
            (RiskAssessment(RiskTier.L2, 0.9, "頭很暈", ["llm"]), _day_ts(9)),  # L2 已即時通知
            _l1(FAILSAFE_EVENT_REASON, _day_ts(11), signals=["llm:error"]),  # 系統故障留痕
            _l1("前天的小訊號", _day_ts(10) - 86400.0),  # 不在摘要日
            _l1("心情低落", _day_ts(12)),
        ]
    )
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
        risk_events=events,
    )
    system_prompt = summarizer.calls[0][0]
    assert "心情低落" in system_prompt
    assert "頭很暈" not in system_prompt
    assert FAILSAFE_EVENT_REASON not in system_prompt
    assert "前天的小訊號" not in system_prompt


def test_summary_prompt_unchanged_without_signals():
    summaries = FakeConversationSummaryStore()
    summarizer = _StubSummarizer()
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=summarizer,
        summaries=summaries,
        clock=lambda: NOW,
        risk_events=_events_store([]),
    )
    from kinsun.reports.summaries import SUMMARY_PROMPT

    assert summarizer.calls[0][0] == SUMMARY_PROMPT


def test_summary_backward_compatible_without_risk_events():
    summaries = FakeConversationSummaryStore()
    summarize_day(
        "u1",
        short_term=_ShortTerm([Message("user", "嗨")]),
        summarizer=_StubSummarizer(),
        summaries=summaries,
        clock=lambda: NOW,
    )
    assert len(summaries.list_for_elder("u1")) == 1
