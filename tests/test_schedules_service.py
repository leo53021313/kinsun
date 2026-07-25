"""ScheduleService：group 展開、輸入驗證、上限與取消授權。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kinsun.schedules.models import CreatedBy, Occurrence, RepeatKind, ScheduleKind
from kinsun.schedules.service import ScheduleService, ScheduleValidationError
from kinsun.schedules.store import FakeScheduleStore

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 7, 25, 20, 0, tzinfo=TZ)


def _service(**kw) -> ScheduleService:
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"id{counter['n']}"

    return ScheduleService(
        kw.pop("store", FakeScheduleStore()),
        clock=lambda: NOW,
        new_id=new_id,
        **kw,
    )


def _at(hour: int, minute: int = 0, day: int = 25) -> float:
    return datetime(2026, 7, day, hour, minute, tzinfo=TZ).timestamp()


def test_create_one_alarm_returns_one_row_grouped_to_itself():
    rows = _service().create(
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="去吃飯",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.ONCE, scheduled_at=_at(20, 45)),),
    )
    assert len(rows) == 1
    assert rows[0].group_id == rows[0].schedule_id
    assert rows[0].created_by == CreatedBy.ELDER


def test_create_many_alarms_share_one_group():
    # 同一顆藥早晚各一個鬧鐘：兩列、同 group，家屬刪「這個藥」才能一次刪乾淨。
    rows = _service().create(
        elder_id="e1",
        kind=ScheduleKind.MEDICATION,
        title="血壓藥",
        created_by=CreatedBy.GUARDIAN,
        occurrences=(
            Occurrence(RepeatKind.DAILY, repeat_time="08:00"),
            Occurrence(RepeatKind.DAILY, repeat_time="21:00"),
        ),
    )
    assert len(rows) == 2
    assert len({r.group_id for r in rows}) == 1
    assert {r.repeat_time for r in rows} == {"08:00", "21:00"}


def test_create_sets_audience_from_kind_not_author():
    rows = _service().create(
        elder_id="e1",
        kind=ScheduleKind.APPOINTMENT,
        title="心臟科回診",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.ONCE, scheduled_at=_at(9, 0, day=30)),),
        event_at=_at(10, 30, day=30),
    )
    assert rows[0].audience.value == "elder_and_guardian"
    assert rows[0].event_at == _at(10, 30, day=30)


def test_create_persists_to_store():
    store = FakeScheduleStore()
    _service(store=store).create(
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="散步",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.DAILY, repeat_time="17:00"),),
    )
    assert len(store.list_for_elder("e1")) == 1


def test_create_strips_whitespace_from_title():
    rows = _service().create(
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="  去吃飯  ",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.ONCE, scheduled_at=_at(20, 45)),),
    )
    assert rows[0].title == "去吃飯"


def test_create_rejects_blank_title():
    with pytest.raises(ScheduleValidationError, match="事情"):
        _service().create(
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="   ",
            created_by=CreatedBy.ELDER,
            occurrences=(Occurrence(RepeatKind.ONCE, scheduled_at=_at(21)),),
        )


def test_create_rejects_empty_occurrences():
    with pytest.raises(ScheduleValidationError, match="時間"):
        _service().create(
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="散步",
            created_by=CreatedBy.ELDER,
            occurrences=(),
        )


def test_create_rejects_time_in_the_past():
    with pytest.raises(ScheduleValidationError, match="過去"):
        _service().create(
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="去吃飯",
            created_by=CreatedBy.ELDER,
            occurrences=(Occurrence(RepeatKind.ONCE, scheduled_at=_at(19)),),
        )


def test_create_rejects_once_without_a_time():
    with pytest.raises(ScheduleValidationError, match="確切時間"):
        _service().create(
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="去吃飯",
            created_by=CreatedBy.ELDER,
            occurrences=(Occurrence(RepeatKind.ONCE),),
        )


def test_create_rejects_time_too_far_ahead():
    with pytest.raises(ScheduleValidationError, match="太遠"):
        _service(max_days_ahead=7).create(
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="去吃飯",
            created_by=CreatedBy.ELDER,
            occurrences=(Occurrence(RepeatKind.ONCE, scheduled_at=_at(20) + 30 * 86400),),
        )


def test_create_rejects_malformed_repeat_time():
    with pytest.raises(ScheduleValidationError, match="時刻"):
        _service().create(
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="散步",
            created_by=CreatedBy.ELDER,
            occurrences=(Occurrence(RepeatKind.DAILY, repeat_time="25:99"),),
        )


def test_create_rejects_weekly_without_weekday():
    with pytest.raises(ScheduleValidationError, match="星期"):
        _service().create(
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="上課",
            created_by=CreatedBy.ELDER,
            occurrences=(Occurrence(RepeatKind.WEEKLY, repeat_time="15:00"),),
        )


def test_create_rejects_when_over_active_limit():
    service = _service(max_active_per_elder=2)
    service.create(
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="散步",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.DAILY, repeat_time="17:00"),),
    )
    with pytest.raises(ScheduleValidationError, match="太多"):
        service.create(
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="喝水",
            created_by=CreatedBy.ELDER,
            occurrences=(
                Occurrence(RepeatKind.DAILY, repeat_time="10:00"),
                Occurrence(RepeatKind.DAILY, repeat_time="14:00"),
            ),
        )


def test_create_writes_nothing_when_limit_exceeded():
    # 超過上限時一列都不該寫進去，否則長輩會拿到「半組」鬧鐘：早上會響、晚上不會。
    store = FakeScheduleStore()
    with pytest.raises(ScheduleValidationError):
        _service(store=store, max_active_per_elder=1).create(
            elder_id="e1",
            kind=ScheduleKind.MEDICATION,
            title="血壓藥",
            created_by=CreatedBy.GUARDIAN,
            occurrences=(
                Occurrence(RepeatKind.DAILY, repeat_time="08:00"),
                Occurrence(RepeatKind.DAILY, repeat_time="21:00"),
            ),
        )
    assert store.list_for_elder("e1") == []


def test_create_writes_nothing_when_one_occurrence_is_invalid():
    # 驗證是全有全無：第二個鬧鐘壞掉時，第一個也不可以留下來。
    store = FakeScheduleStore()
    with pytest.raises(ScheduleValidationError):
        _service(store=store).create(
            elder_id="e1",
            kind=ScheduleKind.MEDICATION,
            title="血壓藥",
            created_by=CreatedBy.GUARDIAN,
            occurrences=(
                Occurrence(RepeatKind.DAILY, repeat_time="08:00"),
                Occurrence(RepeatKind.DAILY, repeat_time="99:99"),
            ),
        )
    assert store.list_for_elder("e1") == []


def test_elder_cannot_cancel_what_the_family_set_up():
    store = FakeScheduleStore()
    service = _service(store=store)
    rows = service.create(
        elder_id="e1",
        kind=ScheduleKind.MEDICATION,
        title="血壓藥",
        created_by=CreatedBy.GUARDIAN,
        occurrences=(Occurrence(RepeatKind.DAILY, repeat_time="08:00"),),
    )
    with pytest.raises(ScheduleValidationError, match="家人"):
        service.cancel_group(rows[0].group_id, requested_by=CreatedBy.ELDER)
    assert len(store.list_for_elder("e1")) == 1


def test_elder_can_cancel_what_they_set_themselves():
    store = FakeScheduleStore()
    service = _service(store=store)
    rows = service.create(
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="去吃飯",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.ONCE, scheduled_at=_at(20, 45)),),
    )
    service.cancel_group(rows[0].group_id, requested_by=CreatedBy.ELDER)
    assert store.list_for_elder("e1") == []


def test_guardian_can_cancel_what_the_elder_set():
    store = FakeScheduleStore()
    service = _service(store=store)
    rows = service.create(
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="去吃飯",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.ONCE, scheduled_at=_at(20, 45)),),
    )
    service.cancel_group(rows[0].group_id, requested_by=CreatedBy.GUARDIAN)
    assert store.list_for_elder("e1") == []


def test_cancel_unknown_group_is_silent():
    _service().cancel_group("nope", requested_by=CreatedBy.GUARDIAN)  # 不得拋


def test_list_for_elder_delegates_to_store():
    store = FakeScheduleStore()
    service = _service(store=store)
    service.create(
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="散步",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.DAILY, repeat_time="17:00"),),
    )
    assert [s.title for s in service.list_for_elder("e1")] == ["散步"]
