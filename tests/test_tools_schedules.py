"""排程工具：長輩用說的建立、查詢與取消——含三條安全界線。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kinsun.schedules.models import CreatedBy, Occurrence, RepeatKind, ScheduleKind
from kinsun.schedules.service import ScheduleService
from kinsun.schedules.store import FakeScheduleStore
from kinsun.tools.registry import ToolInvocationContext
from kinsun.tools.schedules import (
    build_cancel_handler,
    build_create_handler,
    build_list_handler,
)
from kinsun.turn_context import elder_utterance

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 7, 25, 20, 0, tzinfo=TZ)
CTX = ToolInvocationContext(trace_id="t", elder_id="e1")


def _once_args(title: str) -> dict:
    return {
        "title": title,
        "kind": "custom",
        "repeat": "once",
        "date": "2026-07-25",
        "time": "21:00",
    }


@pytest.fixture
def service_and_store():
    store = FakeScheduleStore()
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"g{counter['n']}"

    return ScheduleService(store, clock=lambda: NOW, new_id=new_id), store


@pytest.fixture(autouse=True)
def _elder_spoke():
    """本模組預設都在「長輩剛開口」的情境下跑——那是寫入型工具的前提（安全界線 4）。

    要測沒開口的那一輪（主動關懷路徑），在測試裡自己用 `elder_utterance("")` 蓋掉。
    """
    with elder_utterance("阿嬤剛剛講的話"):
        yield


@pytest.fixture
def create(service_and_store):
    service, _ = service_and_store
    return build_create_handler(service, clock=lambda: NOW)


# ── 建立 ──


def test_create_a_one_off_reminder(create, service_and_store):
    service, _ = service_and_store
    reply = create(
        _once_args("去吃飯"),
        CTX,
    )
    group = service.groups_for_elder("e1")[0]
    assert group.title == "去吃飯"
    assert group.created_by == CreatedBy.ELDER
    assert "複誦" in reply  # 工具明確要求模型複誦，這是決策 3 的落地點


def test_advance_minutes_moves_the_alarm_before_the_event(create, service_and_store):
    # 決策 9：提前量由金孫提議、長輩認可；事件九點、提醒八點四十五。
    service, _ = service_and_store
    create(
        {
            "title": "出門",
            "kind": "custom",
            "repeat": "once",
            "date": "2026-07-25",
            "time": "21:00",
            "advance_minutes": 15,
        },
        CTX,
    )
    schedule = service.groups_for_elder("e1")[0].schedules[0]
    assert schedule.scheduled_at == datetime(2026, 7, 25, 20, 45, tzinfo=TZ).timestamp()
    assert schedule.event_at == datetime(2026, 7, 25, 21, 0, tzinfo=TZ).timestamp()


def test_no_advance_leaves_event_at_empty(create, service_and_store):
    # event_at 留空＝措辭走「提醒您」而不是「再過 n 分鐘」。
    service, _ = service_and_store
    create(
        _once_args("看電視"),
        CTX,
    )
    assert service.groups_for_elder("e1")[0].schedules[0].event_at is None


def test_in_minutes_is_relative_to_now(create, service_and_store):
    service, _ = service_and_store
    create({"title": "關瓦斯", "kind": "custom", "repeat": "once", "in_minutes": 30}, CTX)
    schedule = service.groups_for_elder("e1")[0].schedules[0]
    assert schedule.scheduled_at == datetime(2026, 7, 25, 20, 30, tzinfo=TZ).timestamp()


def test_create_daily(create, service_and_store):
    service, _ = service_and_store
    create({"title": "量血壓", "kind": "custom", "repeat": "daily", "time": "07:00"}, CTX)
    schedule = service.groups_for_elder("e1")[0].schedules[0]
    assert schedule.repeat_kind == RepeatKind.DAILY
    assert schedule.repeat_time == "07:00"


def test_create_weekly(create, service_and_store):
    service, _ = service_and_store
    args = {"title": "上課", "kind": "custom", "repeat": "weekly", "time": "15:00", "weekday": 2}
    create(args, CTX)
    assert service.groups_for_elder("e1")[0].schedules[0].repeat_weekday == 2


def test_medication_kind_is_kept(create, service_and_store):
    # 決策 7：長輩說「提醒我吃血壓藥」標 medication，健康報告才不會漏算。
    service, _ = service_and_store
    create({"title": "血壓藥", "kind": "medication", "repeat": "daily", "time": "08:00"}, CTX)
    group = service.groups_for_elder("e1")[0]
    assert group.kind == ScheduleKind.MEDICATION
    assert group.created_by == CreatedBy.ELDER


def test_unknown_kind_falls_back_to_custom(create, service_and_store):
    service, _ = service_and_store
    create({"title": "散步", "kind": "exercise", "repeat": "daily", "time": "17:00"}, CTX)
    assert service.groups_for_elder("e1")[0].kind == ScheduleKind.CUSTOM


def test_past_time_is_refused_in_plain_words(create, service_and_store):
    service, _ = service_and_store
    reply = create(
        {**_once_args("來不及"), "date": "2020-01-01", "time": "10:00"},
        CTX,
    )
    assert "過去" in reply
    assert service.groups_for_elder("e1") == []


def test_malformed_time_is_refused(create, service_and_store):
    service, _ = service_and_store
    reply = create({"title": "散步", "kind": "custom", "repeat": "daily", "time": "晚上"}, CTX)
    assert "沒辦法記下來" in reply
    assert service.groups_for_elder("e1") == []


def test_over_the_limit_is_refused(service_and_store):
    store = FakeScheduleStore()
    service = ScheduleService(store, clock=lambda: NOW, max_active_per_elder=1)
    create = build_create_handler(service, clock=lambda: NOW)
    create({"title": "第一件", "kind": "custom", "repeat": "daily", "time": "08:00"}, CTX)
    reply = create({"title": "第二件", "kind": "custom", "repeat": "daily", "time": "09:00"}, CTX)
    assert "太多" in reply


# ── 安全界線 1：對象只認 context ──


def test_elder_id_in_arguments_is_ignored(create, service_and_store):
    """模型若能指定對象，就等於能改別人的排程。

    這是全庫第一個會寫資料庫的工具，這條界線是它最重要的一條。
    """
    service, _ = service_and_store
    create(
        {
            "title": "偷塞的",
            "kind": "custom",
            "repeat": "daily",
            "time": "08:00",
            "elder_id": "somebody-else",
        },
        CTX,
    )
    assert service.groups_for_elder("e1")[0].title == "偷塞的"
    assert service.groups_for_elder("somebody-else") == []


def test_without_a_context_nothing_is_written(create, service_and_store):
    service, _ = service_and_store
    args = {"title": "沒有對象", "kind": "custom", "repeat": "daily", "time": "08:00"}
    reply = create(args, None)
    assert "不知道是誰" in reply
    assert service.groups_for_elder("e1") == []


# ── 安全界線 4：長輩沒開口的那一輪不得寫入 ──
#
# 主動關懷（`CareAgent.proactive`）也走工具迴圈，且把原話明確設為空字串。那一輪長輩
# 根本沒說話，任何寫入都不可能得到他的同意。比照 `weather._is_from_elder` 的做法，
# 防線放在工具內、以 `current_utterance()` 判定。


def test_create_refuses_when_the_elder_never_spoke(create, service_and_store):
    service, _ = service_and_store
    with elder_utterance(""):  # 主動關懷路徑：agent.proactive 就是這樣設的
        reply = create(_once_args("長輩沒答應的事"), CTX)
    assert "沒有開口" in reply
    assert service.groups_for_elder("e1") == []


def test_cancel_refuses_when_the_elder_never_spoke(create, service_and_store):
    service, _ = service_and_store
    create(_once_args("去吃飯"), CTX)  # 長輩自己設的（autouse fixture 供原話）
    with elder_utterance(""):
        reply = build_cancel_handler(service)({"group_id": "g1"}, CTX)
    assert "沒有開口" in reply
    assert service.groups_for_elder("e1")[0].title == "去吃飯"  # 沒被取消


def test_list_is_allowed_without_an_utterance(create, service_and_store):
    """唯讀工具不受此界線約束——問候要看得到今天有什麼事才講得出話。"""
    service, _ = service_and_store
    create(_once_args("去吃飯"), CTX)
    with elder_utterance(""):
        reply = build_list_handler(service, clock=lambda: NOW)({}, CTX)
    assert "去吃飯" in reply


# ── 查詢 ──


def test_list_is_empty_at_first(service_and_store):
    service, _ = service_and_store
    assert "沒有任何提醒" in build_list_handler(service, clock=lambda: NOW)({}, CTX)


def test_list_shows_each_thing_with_its_id(create, service_and_store):
    service, _ = service_and_store
    create({"title": "散步", "kind": "custom", "repeat": "daily", "time": "17:00"}, CTX)
    reply = build_list_handler(service, clock=lambda: NOW)({}, CTX)
    assert "每天 17:00 散步" in reply
    assert "編號 g1" in reply


def test_list_is_scoped_to_the_speaker(create, service_and_store):
    service, _ = service_and_store
    create({"title": "散步", "kind": "custom", "repeat": "daily", "time": "17:00"}, CTX)
    other = ToolInvocationContext(trace_id="t", elder_id="e2")
    assert "沒有任何提醒" in build_list_handler(service, clock=lambda: NOW)({}, other)


# ── 取消：安全界線 2 與 3 ──


def test_cancel_what_the_elder_set_himself(create, service_and_store):
    service, _ = service_and_store
    create({"title": "散步", "kind": "custom", "repeat": "daily", "time": "17:00"}, CTX)
    reply = build_cancel_handler(service)({"group_id": "g1"}, CTX)
    assert "已經取消" in reply
    assert service.groups_for_elder("e1") == []


def test_cannot_cancel_what_the_family_set_up(service_and_store):
    """吃藥與回診是家人替他把關的事，一句話就刪掉等於幫他停藥。"""
    service, _ = service_and_store
    rows = service.create(
        elder_id="e1",
        kind=ScheduleKind.MEDICATION,
        title="血壓藥",
        created_by=CreatedBy.GUARDIAN,
        occurrences=(Occurrence(RepeatKind.DAILY, repeat_time="08:00"),),
    )
    reply = build_cancel_handler(service)({"group_id": rows[0].group_id}, CTX)
    assert "家人" in reply
    assert len(service.groups_for_elder("e1")) == 1


def test_cannot_cancel_another_elders_schedule(create, service_and_store):
    # 不比對名下就等於誰都能拿別人的 group_id 來刪。
    service, _ = service_and_store
    create({"title": "散步", "kind": "custom", "repeat": "daily", "time": "17:00"}, CTX)
    other = ToolInvocationContext(trace_id="t", elder_id="e2")
    reply = build_cancel_handler(service)({"group_id": "g1"}, other)
    assert "找不到" in reply
    assert len(service.groups_for_elder("e1")) == 1


def test_cancel_unknown_id_is_explained(create, service_and_store):
    service, _ = service_and_store
    assert "找不到" in build_cancel_handler(service)({"group_id": "nope"}, CTX)
