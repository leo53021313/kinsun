import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")


def test_elder_and_invite_roundtrip():
    from kinsun.accounts.models import Elder, Invite, InviteRole
    from kinsun.accounts.repository import PgAccountRepository
    from kinsun.db import ensure_schema

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    repo = PgAccountRepository(url)
    repo.save_elder(Elder("e1", "王大明", None))
    assert repo.get_elder("e1").name == "王大明"
    repo.save_invite(Invite("code1", "e1", InviteRole.ELDER, 9999999999.0, 5, 0, None))
    assert repo.get_invite("code1").elder_id == "e1"
