"""時間情境注入：白話講法 ＋ 每輪重算 ＋ 真的進得了 system prompt。

格式斷言自 `tests/test_tools_clock.py` 移植（工具已於 2026-07-25 移除）：那些講法是
長輩耳朵聽到的字，改工具為注入不代表可以順手改措辭，故一字不動地留下守門。
"""

from datetime import datetime, timedelta, timezone

from kinsun.clock import TimeFacts, format_taiwan_time
from kinsun.memory.recall import SessionMemory
from kinsun.memory.shortterm import FakeMemoryStore
from tests.fakes import FakeLongTermStore

_TZ = timezone(timedelta(hours=8))


def _fixed(dt: datetime):
    return lambda: dt


# ── 白話講法（自 test_tools_clock.py 移植）──


def test_format_afternoon():
    out = format_taiwan_time(datetime(2026, 7, 3, 14, 30, tzinfo=_TZ))
    assert "2026年7月3日" in out
    assert "星期五" in out  # 2026-07-03 為星期五
    assert "下午2點30分" in out


def test_format_noon_on_the_hour():
    assert "中午12點整" in format_taiwan_time(datetime(2026, 7, 3, 12, 0, tzinfo=_TZ))


def test_format_morning_single_digit_minute():
    assert "上午9點5分" in format_taiwan_time(datetime(2026, 7, 3, 9, 5, tzinfo=_TZ))


def test_format_midnight_is_before_dawn():
    assert "凌晨12點15分" in format_taiwan_time(datetime(2026, 7, 3, 0, 15, tzinfo=_TZ))


def test_format_evening():
    assert "晚上8點12分" in format_taiwan_time(datetime(2026, 7, 25, 20, 12, tzinfo=_TZ))


# ── 事實段 ──


def test_facts_section_carries_the_current_time():
    section = TimeFacts(clock=_fixed(datetime(2026, 7, 25, 20, 12, tzinfo=_TZ))).facts("elder-1")

    assert section is not None
    assert section.items == ["2026年7月25日 星期六，晚上8點12分"]


def test_facts_title_says_taiwan_time_and_holds_the_line_on_announcing_it():
    """段首兩件事缺一不可：講明是台灣時間；擋掉「看到就報時」。

    後者是位置注入付過的學費（locations/facts.py）——注入什麼，模型就傾向講什麼。
    """
    section = TimeFacts(clock=_fixed(datetime(2026, 7, 25, 20, 12, tzinfo=_TZ))).facts("elder-1")

    assert "台灣時間" in section.title
    assert "沒問就不用特地報時" in section.title


def test_facts_is_never_empty():
    """時間永遠存在（不像用藥可能沒設），故不回 None——每一輪都必須有這段。"""
    assert TimeFacts(clock=_fixed(datetime(2026, 7, 25, 20, 12, tzinfo=_TZ))).facts("") is not None


def test_facts_rereads_the_clock_every_turn():
    """本功能的核心：時間是每輪現算的，不是啟動時算一次就凍住。"""
    ticks = iter(
        [
            datetime(2026, 7, 25, 20, 12, tzinfo=_TZ),
            datetime(2026, 7, 25, 21, 30, tzinfo=_TZ),
        ]
    )
    facts = TimeFacts(clock=lambda: next(ticks))

    assert facts.facts("elder-1").items == ["2026年7月25日 星期六，晚上8點12分"]
    assert facts.facts("elder-1").items == ["2026年7月25日 星期六，晚上9點30分"]


# ── 接線：時間真的進得了送給模型的 system prompt ──


def test_time_reaches_the_system_prompt_through_session_memory():
    now = datetime(2026, 7, 25, 20, 12, tzinfo=_TZ)
    session = SessionMemory(
        FakeMemoryStore(now=now),
        FakeLongTermStore(),
        facts=[TimeFacts(clock=_fixed(now))],
    )

    suffix = session.assemble("elder-1", "現在幾點").system_suffix

    assert "台灣時間" in suffix
    assert "2026年7月25日 星期六，晚上8點12分" in suffix
