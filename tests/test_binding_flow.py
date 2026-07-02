from datetime import datetime, timedelta, timezone
from itertools import count

from kinsun.accounts.models import ConsentBy, InviteRole
from kinsun.accounts.service import AccountService
from kinsun.appointments.flow import AppointmentMenu
from kinsun.appointments.service import AppointmentService
from kinsun.binding.flow import BindingFlow
from kinsun.medications.flow import MedicationMenu
from kinsun.medications.service import MedicationService
from tests.fakes import (
    FakeAccountStore,
    FakeAppointmentStore,
    FakeBindingSessionStore,
    FakeMedicationStore,
)

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 6, 29, 10, 0, tzinfo=TPE)


class _FakeProfiles:
    def __init__(self, name="王家屬"):
        self._name = name

    def display_name(self, line_user_id):
        return self._name


def _build_flow(accounts, sessions, profiles, *, clock, on_guardian_bound=None):
    med_ids = (f"m{i}" for i in count(1))
    medications = MedicationService(FakeMedicationStore(), new_id=lambda: next(med_ids))
    menu = MedicationMenu(medications, accounts, sessions, clock=clock)
    appt_ids = (f"a{i}" for i in count(1))
    appointments = AppointmentService(FakeAppointmentStore(), new_id=lambda: next(appt_ids))
    appt_menu = AppointmentMenu(appointments, accounts, sessions, clock=clock)
    return BindingFlow(
        accounts,
        sessions,
        profiles,
        menu,
        appt_menu,
        clock=clock,
        session_ttl_seconds=600,
        on_guardian_bound=on_guardian_bound,
    )


def _flow(repo=None, *, now=NOW, profiles=None, code="ABCDEFGHIJKLMNOP", on_guardian_bound=None):
    repo = repo or FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: now, new_id=lambda: next(ids), new_code=lambda: code
    )
    sessions = FakeBindingSessionStore()
    flow = _build_flow(
        accounts,
        sessions,
        profiles or _FakeProfiles(),
        clock=lambda: now,
        on_guardian_bound=on_guardian_bound,
    )
    return flow, accounts, repo


def test_non_binding_text_returns_none():
    flow, _, _ = _flow()
    assert flow.handle("U-1", "今天天氣真好") is None


def test_trigger_opens_menu():
    flow, _, _ = _flow()
    reply = flow.handle("U-1", "設定")
    assert "建立長輩" in reply and "綁定" in reply


def test_flow1_create_elder_returns_code_and_uses_display_name():
    flow, accounts, repo = _flow(profiles=_FakeProfiles("林小明"))
    flow.handle("U-son", "設定")
    flow.handle("U-son", "1")
    reply = flow.handle("U-son", "阿公")
    assert "阿公" in reply and "ABCDEFGHIJKLMNOP" in reply
    assert repo.get_guardian_by_line("U-son").name == "林小明"
    assert [e.name for e in accounts.elders_managed_by("U-son")] == ["阿公"]


def test_menu_invalid_choice():
    flow, _, _ = _flow()
    flow.handle("U-1", "設定")
    assert "1" in flow.handle("U-1", "9")


def test_flow2_no_elders_prompts_create():
    flow, _, _ = _flow()
    flow.handle("U-x", "設定")
    assert "還沒有長輩" in flow.handle("U-x", "2")


def test_flow2_one_elder_issues_guardian_code():
    flow, accounts, repo = _flow()
    accounts.create_elder("U-son", "兒子", "阿公")
    flow.handle("U-son", "設定")
    assert "家人邀請碼" in flow.handle("U-son", "2")


def test_flow3_redeem_elder_via_menu():
    flow, accounts, repo = _flow()
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    inv = accounts.generate_invite(elder.elder_id, InviteRole.ELDER)
    flow.handle("U-elder", "設定")
    flow.handle("U-elder", "3")
    confirm = flow.handle("U-elder", inv.code)
    assert "阿公" in confirm and "同意" in confirm
    assert "綁定成功" in flow.handle("U-elder", "是")
    assert repo.get_elder(elder.elder_id).line_user_id == "U-elder"
    assert repo.get_consent(elder.elder_id).consent_by == ConsentBy.SELF


def test_flow3_auto_detect_pasted_code():
    flow, accounts, repo = _flow()
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    inv = accounts.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    confirm = flow.handle("U-daughter", inv.code)
    assert "阿公" in confirm
    assert "綁定成功" in flow.handle("U-daughter", "是")


def test_flow3_used_code_message():
    flow, accounts, repo = _flow()
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    inv = accounts.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    accounts.redeem_invite(inv.code, "U-d1", consent_by=ConsentBy.SELF)
    flow.handle("U-d2", "設定")
    flow.handle("U-d2", "3")
    assert "使用過" in flow.handle("U-d2", inv.code)


def test_flow3_confirm_no_cancels():
    flow, accounts, repo = _flow()
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    inv = accounts.generate_invite(elder.elder_id, InviteRole.ELDER)
    flow.handle("U-elder", "設定")
    flow.handle("U-elder", "3")
    flow.handle("U-elder", inv.code)
    assert "取消" in flow.handle("U-elder", "否")
    assert repo.get_elder(elder.elder_id).line_user_id is None


def test_cancel_resets_to_idle():
    flow, _, _ = _flow()
    flow.handle("U-1", "設定")
    assert "取消" in flow.handle("U-1", "取消")
    assert flow.handle("U-1", "隨便") is None


def test_menu_shows_medication_and_delegates():
    flow, _, _ = _flow()
    assert "用藥提醒" in flow.handle("U-1", "設定")
    assert "新增用藥" in flow.handle("U-1", "4")


def test_menu_shows_appointment_and_delegates():
    flow, _, _ = _flow()
    assert "回診提醒" in flow.handle("U-1", "設定")
    assert "新增回診" in flow.handle("U-1", "5")


def test_create_elder_links_menu():
    bound = []
    flow, _, _ = _flow(profiles=_FakeProfiles("林小明"), on_guardian_bound=bound.append)
    flow.handle("U-son", "設定")
    flow.handle("U-son", "1")
    flow.handle("U-son", "阿公")
    assert bound == ["U-son"]


def test_guardian_redeem_links_menu():
    bound = []
    flow, accounts, _ = _flow(on_guardian_bound=bound.append)
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    inv = accounts.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    flow.handle("U-daughter", inv.code)
    flow.handle("U-daughter", "是")
    assert bound == ["U-daughter"]


def test_elder_redeem_does_not_link_menu():
    bound = []
    flow, accounts, _ = _flow(on_guardian_bound=bound.append)
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    inv = accounts.generate_invite(elder.elder_id, InviteRole.ELDER)
    flow.handle("U-elder", "設定")
    flow.handle("U-elder", "3")
    flow.handle("U-elder", inv.code)
    flow.handle("U-elder", "是")
    assert bound == []


def test_link_failure_does_not_break_binding():
    def boom(line):
        raise RuntimeError("link fail")

    flow, accounts, _ = _flow(on_guardian_bound=boom)
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    inv = accounts.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    flow.handle("U-daughter", inv.code)
    assert "綁定成功" in flow.handle("U-daughter", "是")


def test_session_timeout_resets():
    repo = FakeAccountStore()
    now = {"t": NOW}
    ids = (f"id{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: now["t"], new_id=lambda: next(ids), new_code=lambda: "c"
    )
    sessions = FakeBindingSessionStore()
    flow = _build_flow(accounts, sessions, _FakeProfiles(), clock=lambda: now["t"])
    flow.handle("U-1", "設定")
    now["t"] = NOW + timedelta(minutes=11)
    assert flow.handle("U-1", "1") is None
