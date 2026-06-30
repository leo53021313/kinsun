from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.accounts.models import ConsentBy, InviteRole, Role
from kinsun.accounts.service import AccountService, InviteError
from tests.fakes import FakeAccountRepository

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 6, 29, 10, 0, tzinfo=TPE)


def _service(repo, *, now=NOW):
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    return AccountService(
        repo, clock=lambda: now, new_id=lambda: next(ids), new_code=lambda: next(codes)
    )


def test_create_elder_makes_primary_guardian():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    assert elder.name == "阿公"
    eg = repo.list_elder_guardians(elder.elder_id)[0]
    assert eg.role == Role.PRIMARY
    assert eg.escalation_order == 1
    assert eg.can_view_transcript is True


def test_generate_invite_sets_ttl_and_limit():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    assert inv.role == InviteRole.ELDER
    assert inv.max_attempts == 5
    assert inv.expires_at == (NOW + timedelta(hours=24)).timestamp()
    assert repo.get_invite(inv.code) == inv


def test_redeem_elder_binds_line():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    assert repo.get_elder(elder.elder_id).line_user_id == "U-elder"
    assert repo.get_consent(elder.elder_id).consent_by == ConsentBy.SELF
    assert repo.get_invite(inv.code).used_at is not None


def test_redeem_guardian_adds_relation():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-daughter", consent_by=ConsentBy.SELF)
    egs = repo.list_elder_guardians(elder.elder_id)
    assert len(egs) == 2
    assert egs[1].role == Role.GUARDIAN
    assert egs[1].escalation_order == 2
    assert egs[1].can_view_transcript is False


def test_redeem_unknown_code():
    svc = _service(FakeAccountRepository())
    with pytest.raises(InviteError) as exc:
        svc.redeem_invite("nope", "U-x", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "not_found"


def test_redeem_twice_is_used():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    with pytest.raises(InviteError) as exc:
        svc.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "used"


def test_redeem_expired():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    later = _service(repo, now=NOW + timedelta(hours=25))
    with pytest.raises(InviteError) as exc:
        later.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "expired"
    assert repo.get_invite(inv.code).attempts == 1


def test_guardian_redeem_does_not_create_elder_consent():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-daughter", consent_by=ConsentBy.SELF)
    # 家屬綁定不代表長輩本人同意；不應替長輩寫入同意紀錄。
    assert repo.get_consent(elder.elder_id) is None


def test_guardian_redeem_does_not_resurrect_revoked_consent():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv_e = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv_e.code, "U-elder", consent_by=ConsentBy.SELF)
    svc.revoke_consent(elder.elder_id)
    assert svc.is_consented_elder("U-elder") is False
    # 之後有家屬加入，不可「復活」長輩已撤回的同意。
    inv_g = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv_g.code, "U-daughter", consent_by=ConsentBy.SELF)
    assert svc.is_consented_elder("U-elder") is False


def test_revoke_consent_sets_revoked():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    svc.revoke_consent(elder.elder_id)
    assert repo.get_consent(elder.elder_id).revoked_at == NOW.timestamp()


def test_guardians_of_sorted_and_permissions():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-daughter", consent_by=ConsentBy.SELF)
    egs = svc.guardians_of(elder.elder_id)
    assert [e.escalation_order for e in egs] == [1, 2]
    primary, secondary = egs
    assert svc.can_view_transcript(elder.elder_id, primary.guardian_id) is True
    assert svc.can_view_transcript(elder.elder_id, secondary.guardian_id) is False
    assert svc.can_view_transcript(elder.elder_id, "nobody") is False


def test_get_elder():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    assert svc.get_elder(elder.elder_id).name == "阿公"
    assert svc.get_elder("nope") is None


def test_is_consented_elder_lifecycle():
    repo = FakeAccountRepository()
    svc = _service(repo)
    assert svc.is_consented_elder("U-elder") is False
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    assert svc.is_consented_elder("U-elder") is True
    svc.revoke_consent(elder.elder_id)
    assert svc.is_consented_elder("U-elder") is False


def test_is_consented_elder_bound_without_consent():
    from kinsun.accounts.models import Elder

    repo = FakeAccountRepository()
    svc = _service(repo)
    repo.save_elder(Elder("e1", "阿公", "U-elder"))
    assert svc.is_consented_elder("U-elder") is False


def test_preview_invite_valid_and_not_found():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    p = svc.preview_invite(inv.code)
    assert p.role == InviteRole.ELDER
    assert p.elder_name == "阿公"
    assert p.reason is None
    assert svc.preview_invite("nope") is None


def test_preview_invite_expired():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    later = _service(repo, now=NOW + timedelta(hours=25))
    assert later.preview_invite(inv.code).reason == "expired"


def test_preview_invite_used():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    assert svc.preview_invite(inv.code).reason == "used"


def test_elders_managed_by():
    repo = FakeAccountRepository()
    svc = _service(repo)
    assert svc.elders_managed_by("U-son") == []
    elder = svc.create_elder("U-son", "兒子", "阿公")
    managed = svc.elders_managed_by("U-son")
    assert [e.elder_id for e in managed] == [elder.elder_id]


def test_guardian_line_ids_in_escalation_order():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv_elder = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv_elder.code, "U-elder", consent_by=ConsentBy.SELF)
    inv_guard = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv_guard.code, "U-daughter", consent_by=ConsentBy.SELF)
    assert svc.guardian_line_ids("U-elder") == ["U-son", "U-daughter"]


def test_guardian_line_ids_unbound_elder_returns_empty():
    repo = FakeAccountRepository()
    svc = _service(repo)
    assert svc.guardian_line_ids("U-nobody") == []


def test_guardian_line_ids_only_primary():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv_elder = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv_elder.code, "U-elder", consent_by=ConsentBy.SELF)
    assert svc.guardian_line_ids("U-elder") == ["U-son"]


def test_create_elder_uses_repo_transaction():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    # create_elder 同時寫 elder 與 elder_guardian，且兩者皆落地
    assert repo.get_elder(elder.elder_id).name == "阿公"
    assert repo.list_elder_guardians(elder.elder_id)[0].role.value == "primary"


def test_elder_by_line():
    from kinsun.accounts.models import Elder

    repo = FakeAccountRepository()
    repo.save_elder(Elder("e1", "阿公", "U-elder"))
    svc = _service(repo)
    assert svc.elder_by_line("U-elder").elder_id == "e1"
    assert svc.elder_by_line("nope") is None


def test_guardian_line_ids_of_elder_by_id():
    repo = FakeAccountRepository()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-daughter", consent_by=ConsentBy.SELF)
    # 用 elder_id 直接查，不需長輩本人綁定 LINE
    assert svc.guardian_line_ids_of_elder(elder.elder_id) == ["U-son", "U-daughter"]
    assert svc.guardian_line_ids_of_elder("nope") == []
