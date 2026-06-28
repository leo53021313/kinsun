from kinsun.accounts.models import (
    Consent,
    ConsentBy,
    Elder,
    ElderGuardian,
    Guardian,
    Invite,
    InviteRole,
    Role,
)
from kinsun.accounts.repository import SqliteAccountRepository


def _repo():
    return SqliteAccountRepository(":memory:")


def test_elder_round_trip():
    repo = _repo()
    repo.save_elder(Elder("e1", "阿公", "U-elder"))
    assert repo.get_elder("e1") == Elder("e1", "阿公", "U-elder")
    assert repo.get_elder("nope") is None


def test_guardian_by_line():
    repo = _repo()
    repo.save_guardian(Guardian("g1", "U-1", "兒子"))
    assert repo.get_guardian_by_line("U-1") == Guardian("g1", "U-1", "兒子")
    assert repo.get_guardian_by_line("U-x") is None


def test_elder_guardians_sorted():
    repo = _repo()
    repo.save_elder_guardian(ElderGuardian("e1", "g2", Role.GUARDIAN, 2, False))
    repo.save_elder_guardian(ElderGuardian("e1", "g1", Role.PRIMARY, 1, True))
    rows = repo.list_elder_guardians("e1")
    assert [r.guardian_id for r in rows] == ["g1", "g2"]
    assert repo.get_elder_guardian("e1", "g1").can_view_transcript is True
    assert repo.get_elder_guardian("e1", "nope") is None


def test_consent_round_trip():
    repo = _repo()
    repo.save_consent(Consent("e1", ConsentBy.SELF, "1.0", 10.0))
    assert repo.get_consent("e1") == Consent("e1", ConsentBy.SELF, "1.0", 10.0, None)


def test_invite_round_trip():
    repo = _repo()
    inv = Invite("c1", "e1", InviteRole.ELDER, 100.0, max_attempts=5)
    repo.save_invite(inv)
    assert repo.get_invite("c1") == inv
    assert repo.get_invite("none") is None
