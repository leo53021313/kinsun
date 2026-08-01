"""提醒設定選單：三種類型共用一個入口。"""

from __future__ import annotations

from datetime import datetime
from itertools import count
from zoneinfo import ZoneInfo

import pytest

from kinsun.schedules.flow import ScheduleMenu
from kinsun.schedules.service import ScheduleService
from kinsun.schedules.store import FakeScheduleStore
from tests.fakes import FakeBindingSessionStore

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=TZ)


class _Elder:
    def __init__(self, elder_id: str, name: str) -> None:
        self.elder_id = elder_id
        self.name = name


class _Accounts:
    def __init__(self, elders: list[_Elder]) -> None:
        self._elders = elders

    def elders_managed_by(self, line_user_id: str) -> list[_Elder]:
        return self._elders


@pytest.fixture
def menu_and_store():
    store = FakeScheduleStore()
    ids = (f"s{i}" for i in count(1))
    service = ScheduleService(store, clock=lambda: NOW, new_id=lambda: next(ids))
    menu = ScheduleMenu(
        service,
        _Accounts([_Elder("e1", "阿嬤")]),
        FakeBindingSessionStore(),
        clock=lambda: NOW,
        slot_hours={"morning": 8, "noon": 12, "evening": 18, "bedtime": 21},
        appointment_hour=8,
    )
    return menu, store, service


def _walk(menu, sessions_owner, replies: list[str]) -> str:
    """依序送出每一句，回傳最後一則回覆。"""
    last = menu.open("U-1")
    for text in replies:
        session = menu._sessions.get("U-1")
        last = menu.step(session, text, "U-1")
    return last


def test_menu_offers_three_actions(menu_and_store):
    menu, _, _ = menu_and_store
    opened = menu.open("U-1")
    assert "新增提醒" in opened
    assert "查看提醒" in opened
    assert "刪除提醒" in opened


def test_add_medication_with_slots(menu_and_store):
    menu, store, service = menu_and_store
    reply = _walk(menu, None, ["1", "1", "血壓藥", "1 3"])
    groups = service.groups_for_elder("e1")
    assert len(groups) == 1
    assert {s.repeat_time for s in groups[0].schedules} == {"08:00", "18:00"}
    assert "血壓藥" in reply


def test_add_medication_accepts_a_literal_time(menu_and_store):
    # 開放自訂時刻是 D-76 決策 11 的重點：四時段只是預設，不是限制。
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "1", "血壓藥", "07:30"])
    groups = service.groups_for_elder("e1")
    assert [s.repeat_time for s in groups[0].schedules] == ["07:30"]


def test_add_appointment_creates_two_alarms(menu_and_store):
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "2", "心臟科回診", "2026-07-30 10:30"])
    group = service.groups_for_elder("e1")[0]
    assert len(group.schedules) == 2  # 前一天＋當天
    assert group.event_at == datetime(2026, 7, 30, 10, 30, tzinfo=TZ).timestamp()
    assert group.kind.value == "appointment"


def test_add_appointment_puts_the_day_before_alarm_on_the_day_before(menu_and_store):
    """回診日 2026-07-30 的前一天是 07-29——推算與 REST 入口共用同一份（12 §9 F-16）。

    ⚠️ 時區釘在斷言裡，不讀執行機器的環境時區。
    """
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "2", "心臟科回診", "2026-07-30 10:30"])
    group = service.groups_for_elder("e1")[0]
    assert sorted(s.scheduled_at for s in group.schedules) == [
        datetime(2026, 7, 29, 8, 0, tzinfo=TZ).timestamp(),
        datetime(2026, 7, 30, 8, 0, tzinfo=TZ).timestamp(),
    ]


def test_tomorrows_appointment_set_in_the_afternoon_is_created_and_the_guardian_is_told():
    """下午設明天的回診：前一天那顆已經過了，只建當天那顆，而且要告訴家屬。

    原本整筆會被服務層擋成「那個時間已經過去了」，家屬只會看到那句話與重問一次日期。
    """
    afternoon = datetime(2026, 7, 25, 15, 0, tzinfo=TZ)
    store = FakeScheduleStore()
    service = ScheduleService(store, clock=lambda: afternoon)
    menu = ScheduleMenu(
        service,
        _Accounts([_Elder("e1", "阿嬤")]),
        FakeBindingSessionStore(),
        clock=lambda: afternoon,
        slot_hours={"morning": 8, "noon": 12, "evening": 18, "bedtime": 21},
        appointment_hour=8,
    )
    reply = _walk(menu, None, ["1", "2", "心臟科回診", "2026-07-26 10:30"])
    group = service.groups_for_elder("e1")[0]
    assert [s.scheduled_at for s in group.schedules] == [
        datetime(2026, 7, 26, 8, 0, tzinfo=TZ).timestamp()
    ]
    assert "前一天" in reply and "08:00" in reply


def test_add_appointment_without_a_time(menu_and_store):
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "2", "牙科", "2026-07-31"])
    group = service.groups_for_elder("e1")[0]
    assert group.event_at == datetime(2026, 7, 31, 0, 0, tzinfo=TZ).timestamp()


def test_add_custom_daily(menu_and_store):
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "3", "去公園散步", "每天 17:00"])
    group = service.groups_for_elder("e1")[0]
    assert group.kind.value == "custom"
    assert [s.repeat_time for s in group.schedules] == ["17:00"]


def test_add_custom_weekly(menu_and_store):
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "3", "上課", "每週三 15:00"])
    schedule = service.groups_for_elder("e1")[0].schedules[0]
    assert schedule.repeat_weekday == 2
    assert schedule.repeat_time == "15:00"


def test_add_custom_once(menu_and_store):
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "3", "去吃飯", "2026-07-30 20:45"])
    schedule = service.groups_for_elder("e1")[0].schedules[0]
    assert schedule.scheduled_at == datetime(2026, 7, 30, 20, 45, tzinfo=TZ).timestamp()


def test_bad_time_reprompts_without_losing_the_title(menu_and_store):
    # 打錯時間不該把前面問到的藥名一起丟掉——長輩的家屬要重打一輪就會放棄。
    menu, _, service = menu_and_store
    reply = _walk(menu, None, ["1", "3", "散步", "亂寫"])
    assert "例如" in reply
    assert service.groups_for_elder("e1") == []
    session = menu._sessions.get("U-1")
    assert session.data["title"] == "散步"


def test_view_lists_every_kind(menu_and_store):
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "1", "血壓藥", "1"])
    reply = _walk(menu, None, ["2"])
    assert "血壓藥（早上）" in reply


def test_view_when_empty(menu_and_store):
    menu, _, _ = menu_and_store
    assert "沒有任何提醒" in _walk(menu, None, ["2"])


def test_delete_cancels_the_whole_thing(menu_and_store):
    menu, _, service = menu_and_store
    _walk(menu, None, ["1", "1", "血壓藥", "1 3"])
    reply = _walk(menu, None, ["3", "1"])
    assert "已刪除" in reply
    assert service.groups_for_elder("e1") == []


def test_a_family_member_can_delete_what_the_elder_created(menu_and_store):
    # 反向（長輩刪家屬設的）才禁止；家屬這一側必須放行。
    from kinsun.schedules.models import CreatedBy, Occurrence, RepeatKind, ScheduleKind

    menu, _, service = menu_and_store
    service.create(
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="長輩自己設的",
        created_by=CreatedBy.ELDER,
        occurrences=(Occurrence(RepeatKind.DAILY, repeat_time="09:00"),),
    )
    _walk(menu, None, ["3", "1"])
    assert service.groups_for_elder("e1") == []


def test_unknown_kind_choice_reprompts(menu_and_store):
    menu, _, _ = menu_and_store
    assert "請回覆 1、2 或 3。" == _walk(menu, None, ["1", "9"])
