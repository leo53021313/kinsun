from datetime import datetime, timedelta, timezone
from itertools import count

from kinsun.accounts.service import AccountService
from kinsun.appointment.flow import AppointmentMenu, _parse_date
from kinsun.appointment.service import AppointmentService
from kinsun.binding.session import BindingState
from tests.fakes import FakeAccountRepository, FakeAppointmentStore, FakeBindingSessionStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 10, 10, 0, tzinfo=TPE)


def _setup():
    repo = FakeAccountRepository()
    ids = (f"id{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c"
    )
    accounts.create_elder("U-son", "兒子", "阿公")
    aids = (f"a{i}" for i in count(1))
    appointments = AppointmentService(FakeAppointmentStore(), new_id=lambda: next(aids))
    sessions = FakeBindingSessionStore()
    menu = AppointmentMenu(appointments, accounts, sessions, clock=lambda: NOW)
    return menu, appointments, accounts, sessions


def test_parse_date():
    assert _parse_date("2026-07-15") == "2026-07-15"
    assert _parse_date(" 2026-7-5 ") == "2026-07-05"
    assert _parse_date("七月") is None


def test_add_flow_happy_path():
    menu, appointments, accounts, sessions = _setup()
    elder = accounts.elders_managed_by("U-son")[0]
    assert "新增回診" in menu.open("U-son")
    menu.step(sessions.get("U-son"), "1", "U-son")
    assert sessions.get("U-son").state == BindingState.APPT_ADD_LABEL
    menu.step(sessions.get("U-son"), "心臟科回診", "U-son")
    assert sessions.get("U-son").state == BindingState.APPT_ADD_DATE
    reply = menu.step(sessions.get("U-son"), "2026-07-20", "U-son")
    assert "心臟科回診" in reply and "2026-07-20" in reply
    appts = appointments.list_for_elder(elder.elder_id)
    assert (appts[0].date, appts[0].label) == ("2026-07-20", "心臟科回診")
    assert sessions.get("U-son") is None


def test_add_invalid_date_reprompts():
    menu, _, _, sessions = _setup()
    menu.open("U-son")
    menu.step(sessions.get("U-son"), "1", "U-son")
    menu.step(sessions.get("U-son"), "回診", "U-son")
    reply = menu.step(sessions.get("U-son"), "明天啦", "U-son")
    assert "格式" in reply
    assert sessions.get("U-son").state == BindingState.APPT_ADD_DATE


def test_add_past_date_reprompts():
    menu, _, _, sessions = _setup()
    menu.open("U-son")
    menu.step(sessions.get("U-son"), "1", "U-son")
    menu.step(sessions.get("U-son"), "回診", "U-son")
    reply = menu.step(sessions.get("U-son"), "2026-07-01", "U-son")
    assert "已經過了" in reply
    assert sessions.get("U-son").state == BindingState.APPT_ADD_DATE


def test_view_upcoming_only():
    menu, appointments, accounts, sessions = _setup()
    elder = accounts.elders_managed_by("U-son")[0]
    appointments.add(elder.elder_id, "2026-07-20", "心臟科回診")
    appointments.add(elder.elder_id, "2026-07-01", "舊回診")
    menu.open("U-son")
    reply = menu.step(sessions.get("U-son"), "2", "U-son")
    assert "心臟科回診" in reply and "舊回診" not in reply
    assert sessions.get("U-son") is None


def test_view_empty():
    menu, _, _, sessions = _setup()
    menu.open("U-son")
    assert "沒有即將到來的回診" in menu.step(sessions.get("U-son"), "2", "U-son")


def test_delete_flow():
    menu, appointments, accounts, sessions = _setup()
    elder = accounts.elders_managed_by("U-son")[0]
    appointments.add(elder.elder_id, "2026-07-20", "心臟科回診")
    menu.open("U-son")
    listing = menu.step(sessions.get("U-son"), "3", "U-son")
    assert "1. 2026-07-20 心臟科回診" in listing
    reply = menu.step(sessions.get("U-son"), "1", "U-son")
    assert "已刪除" in reply
    assert appointments.list_for_elder(elder.elder_id) == []
