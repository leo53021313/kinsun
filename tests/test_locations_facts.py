"""LocationFacts：把長輩目前地點注入情境的一段，過期則完全不注入。"""

from datetime import datetime, timedelta, timezone

from kinsun.locations.facts import LocationFacts
from kinsun.locations.store import ElderLocation, FakeLocationStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 17, 12, 0, tzinfo=TPE)


def _facts(location: ElderLocation | None, *, stale_after_hours: int = 2) -> LocationFacts:
    store = FakeLocationStore()
    if location is not None:
        store.save(location)
    return LocationFacts(store, clock=lambda: NOW, stale_after_hours=stale_after_hours)


def _at(*, minutes_ago: float) -> float:
    return (NOW - timedelta(minutes=minutes_ago)).timestamp()


def test_returns_none_when_no_location_recorded():
    assert _facts(None).facts("e1") is None


def test_injects_place_with_relative_time():
    section = _facts(ElderLocation("e1", "台南市", _at(minutes_ago=3))).facts("e1")
    assert section is not None
    assert section.items == ["3 分鐘前在台南市"]


def test_title_frames_location_as_hint_not_answer():
    # ⚠️ anchoring 防線：措辭是功能本體，不是文案。刪掉「參考」等於讓模型
    # 把所在地當答案，正是本設計要防的事。
    section = _facts(ElderLocation("e1", "台南市", _at(minutes_ago=3))).facts("e1")
    assert section is not None
    assert "參考" in section.title
    assert "不一定" in section.title


def test_returns_none_when_stale():
    assert _facts(ElderLocation("e1", "台南市", _at(minutes_ago=121))).facts("e1") is None


def test_boundary_exactly_at_threshold_is_still_trusted():
    # 剛好 2 小時仍採信；門檻是「超過才丟」，不是「到了就丟」。
    section = _facts(ElderLocation("e1", "台南市", _at(minutes_ago=120))).facts("e1")
    assert section is not None
    assert section.items == ["2 小時前在台南市"]


def test_just_now_reads_naturally():
    section = _facts(ElderLocation("e1", "台南市", _at(minutes_ago=0.5))).facts("e1")
    assert section is not None
    assert section.items == ["剛剛在台南市"]


def test_over_an_hour_reads_in_hours():
    section = _facts(ElderLocation("e1", "高雄市", _at(minutes_ago=90))).facts("e1")
    assert section is not None
    assert section.items == ["1 小時前在高雄市"]


def test_future_timestamp_is_treated_as_just_now():
    # 手機時鐘快於伺服器時，recorded_at 可能落在未來。負數的「-1 分鐘前」是
    # 胡說八道；退成「剛剛」是誠實的近似（誤差必然小於時鐘偏差本身）。
    section = _facts(ElderLocation("e1", "台南市", _at(minutes_ago=-5))).facts("e1")
    assert section is not None
    assert section.items == ["剛剛在台南市"]
