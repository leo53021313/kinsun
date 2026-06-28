from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.accounts.models import ConsentBy, InviteRole, Role
from kinsun.accounts.repository import SqliteAccountRepository
from kinsun.accounts.service import AccountService, InviteError

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 6, 29, 10, 0, tzinfo=TPE)


def _service(repo, *, now=NOW):
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    return AccountService(
        repo, clock=lambda: now, new_id=lambda: next(ids), new_code=lambda: next(codes)
    )


def test_create_elder_makes_primary_guardian():
    repo = SqliteAccountRepository(":memory:")
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    assert elder.name == "阿公"
    eg = repo.list_elder_guardians(elder.elder_id)[0]
    assert eg.role == Role.PRIMARY
    assert eg.escalation_order == 1
    assert eg.can_view_transcript is True


def test_generate_invite_sets_ttl_and_limit():
    repo = SqliteAccountRepository(":memory:")
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    assert inv.role == InviteRole.ELDER
    assert inv.max_attempts == 5
    assert inv.expires_at == (NOW + timedelta(hours=24)).timestamp()
    assert repo.get_invite(inv.code) == inv


def test_redeem_elder_binds_line():
    repo = SqliteAccountRepository(":memory:")
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    assert repo.get_elder(elder.elder_id).line_user_id == "U-elder"
    assert repo.get_consent(elder.elder_id).consent_by == ConsentBy.SELF
    assert repo.get_invite(inv.code).used_at is not None


def test_redeem_guardian_adds_relation():
    repo = SqliteAccountRepository(":memory:")
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
    svc = _service(SqliteAccountRepository(":memory:"))
    with pytest.raises(InviteError) as exc:
        svc.redeem_invite("nope", "U-x", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "not_found"


def test_redeem_twice_is_used():
    repo = SqliteAccountRepository(":memory:")
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    with pytest.raises(InviteError) as exc:
        svc.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "used"


def test_redeem_expired():
    repo = SqliteAccountRepository(":memory:")
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    later = _service(repo, now=NOW + timedelta(hours=25))
    with pytest.raises(InviteError) as exc:
        later.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "expired"
    assert repo.get_invite(inv.code).attempts == 1
