from datetime import datetime, timedelta, timezone
from itertools import count

from kinsun.accounts.models import InviteRole, Role
from kinsun.accounts.repository import SqliteAccountRepository
from kinsun.accounts.service import AccountService

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
