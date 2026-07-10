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
