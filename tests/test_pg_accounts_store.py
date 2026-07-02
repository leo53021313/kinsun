import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")


def test_elder_and_invite_roundtrip():
    from kinsun.accounts.models import Elder, Invite, InviteRole
    from kinsun.accounts.store import PgAccountRepository
    from kinsun.db import Database, ensure_schema

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    repo = PgAccountRepository(Database.open(url))
    repo.save_elder(Elder("e1", "王大明", None))
    assert repo.get_elder("e1").name == "王大明"
    repo.save_invite(Invite("code1", "e1", InviteRole.ELDER, 9999999999.0, 5, 0, None))
    assert repo.get_invite("code1").elder_id == "e1"


def test_get_elder_by_line_and_get_guardian():
    from kinsun.accounts.models import Elder, Guardian
    from kinsun.accounts.store import PgAccountRepository
    from kinsun.db import Database, ensure_schema

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    repo = PgAccountRepository(Database.open(url))
    repo.save_elder(Elder("e2", "李小華", "U-elder2"))
    repo.save_guardian(Guardian("g2", "U-guard2", "女兒"))
    assert repo.get_elder_by_line("U-elder2").elder_id == "e2"
    assert repo.get_elder_by_line("nope") is None
    assert repo.get_guardian("g2").line_user_id == "U-guard2"
    assert repo.get_guardian("nope") is None


def test_elder_ids_of_guardian():
    from kinsun.accounts.models import ElderGuardian, Role
    from kinsun.accounts.store import PgAccountRepository
    from kinsun.db import Database, ensure_schema

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    repo = PgAccountRepository(Database.open(url))
    repo.save_elder_guardian(ElderGuardian("e3", "g3", Role.PRIMARY, 1, True))
    assert "e3" in repo.elder_ids_of_guardian("g3")
    assert repo.elder_ids_of_guardian("no-such") == []
