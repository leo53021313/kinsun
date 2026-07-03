from datetime import datetime, timedelta, timezone
from itertools import count

from kinsun.accounts.service import AccountService
from kinsun.binding.session import BindingState
from kinsun.medications.flow import MedicationMenu, _parse_slots
from kinsun.medications.models import MedicationSlot
from kinsun.medications.service import MedicationService
from tests.fakes import FakeAccountStore, FakeBindingSessionStore, FakeMedicationStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 6, 29, 10, 0, tzinfo=TPE)


def _setup():
    repo = FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: next(codes)
    )
    accounts.create_elder("U-son", "兒子", "阿公")
    med_ids = (f"m{i}" for i in count(1))
    medications = MedicationService(FakeMedicationStore(), new_id=lambda: next(med_ids))
    sessions = FakeBindingSessionStore()
    menu = MedicationMenu(medications, accounts, sessions, clock=lambda: NOW)
    return menu, medications, accounts, sessions


def test_parse_slots():
    assert _parse_slots("1 3") == (MedicationSlot.MORNING, MedicationSlot.EVENING)
    assert _parse_slots("４") == (MedicationSlot.BEDTIME,)
    assert _parse_slots("不知道") is None


def test_add_single_elder_flow():
    menu, medications, accounts, sessions = _setup()
    elder = accounts.elders_managed_by("U-son")[0]
    assert "新增" in menu.open("U-son")
    menu.step(sessions.get("U-son"), "1", "U-son")
    assert sessions.get("U-son").state == BindingState.MED_ADD_NAME
    menu.step(sessions.get("U-son"), "降血壓藥", "U-son")
    assert sessions.get("U-son").state == BindingState.MED_ADD_SLOTS
    reply = menu.step(sessions.get("U-son"), "1 3", "U-son")
    assert "降血壓藥" in reply and "早上、晚上" in reply
    meds = medications.list_for_elder(elder.elder_id)
    assert meds[0].slots == (MedicationSlot.MORNING, MedicationSlot.EVENING)
    assert sessions.get("U-son") is None


def test_add_invalid_slots_reprompts():
    menu, medications, accounts, sessions = _setup()
    menu.open("U-son")
    menu.step(sessions.get("U-son"), "1", "U-son")
    menu.step(sessions.get("U-son"), "藥", "U-son")
    reply = menu.step(sessions.get("U-son"), "九", "U-son")
    assert "1" in reply
    assert sessions.get("U-son").state == BindingState.MED_ADD_SLOTS


def test_view_lists_meds():
    menu, medications, accounts, sessions = _setup()
    elder = accounts.elders_managed_by("U-son")[0]
    medications.save(elder.elder_id, "鈣片", (MedicationSlot.BEDTIME,))
    menu.open("U-son")
    reply = menu.step(sessions.get("U-son"), "2", "U-son")
    assert "鈣片" in reply and "睡前" in reply
    assert sessions.get("U-son") is None


def test_view_empty():
    menu, medications, accounts, sessions = _setup()
    menu.open("U-son")
    assert "沒有設定用藥" in menu.step(sessions.get("U-son"), "2", "U-son")


def test_delete_flow():
    menu, medications, accounts, sessions = _setup()
    elder = accounts.elders_managed_by("U-son")[0]
    medications.save(elder.elder_id, "鈣片", (MedicationSlot.BEDTIME,))
    menu.open("U-son")
    listing = menu.step(sessions.get("U-son"), "3", "U-son")
    assert "1. 鈣片" in listing
    reply = menu.step(sessions.get("U-son"), "1", "U-son")
    assert "已刪除" in reply
    assert medications.list_for_elder(elder.elder_id) == []


def test_no_elders_prompts_create():
    repo = FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c"
    )
    medications = MedicationService(FakeMedicationStore(), new_id=lambda: "m")
    sessions = FakeBindingSessionStore()
    menu = MedicationMenu(medications, accounts, sessions, clock=lambda: NOW)
    menu.open("U-x")
    assert "還沒有長輩" in menu.step(sessions.get("U-x"), "1", "U-x")
