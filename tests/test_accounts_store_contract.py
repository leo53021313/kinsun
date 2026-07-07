"""AccountStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員」關係斷言而互不干擾。

不涵蓋 transaction() 回滾：FakeAccountStore 的 `transaction()` 為 no-op（不落實
回滾語意），交易行為不在本合約範圍。所有方法皆以 `tx=None` 呼叫（兩個 adapter 皆支援）。
"""

from __future__ import annotations

import pytest

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
from kinsun.accounts.store import FakeAccountStore, PgAccountStore


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgAccountStore(request.getfixturevalue("pg_database"))
    return FakeAccountStore()


def test_elder_roundtrip_and_by_line(store, ns):
    store.save_elder(Elder(f"{ns}e1", "阿公", f"{ns}U-elder"))
    got = store.get_elder(f"{ns}e1")
    assert got.name == "阿公"
    assert got.line_user_id == f"{ns}U-elder"
    assert store.get_elder_by_line(f"{ns}U-elder").elder_id == f"{ns}e1"
    assert store.get_elder_by_line(f"{ns}nope") is None


def test_guardian_roundtrip_and_by_line(store, ns):
    store.save_guardian(Guardian(f"{ns}g1", f"{ns}U-guard", "女兒"))
    assert store.get_guardian(f"{ns}g1").line_user_id == f"{ns}U-guard"
    assert store.get_guardian(f"{ns}nope") is None
    by_line = store.get_guardian_by_line(f"{ns}U-guard")
    assert by_line.guardian_id == f"{ns}g1"
    assert by_line.name == "女兒"


def test_elder_guardians_ordered_by_escalation(store, ns):
    elder_id = f"{ns}e1"
    # 存入順序刻意與 escalation_order 相反，證明回傳依 escalation_order 排序而非存入順序。
    store.save_elder_guardian(ElderGuardian(elder_id, f"{ns}g2", Role.GUARDIAN, 2, False))
    store.save_elder_guardian(ElderGuardian(elder_id, f"{ns}g1", Role.PRIMARY, 1, True))
    egs = store.list_elder_guardians(elder_id)
    assert [e.guardian_id for e in egs] == [f"{ns}g1", f"{ns}g2"]
    assert [e.escalation_order for e in egs] == [1, 2]
    assert f"{ns}e1" in store.elder_ids_of_guardian(f"{ns}g1")
    assert store.elder_ids_of_guardian(f"{ns}nope") == []


def test_consent_roundtrip(store, ns):
    store.save_consent(Consent(f"{ns}e1", ConsentBy.SELF, "v1", 1000.0, None))
    got = store.get_consent(f"{ns}e1")
    assert got.consent_by == ConsentBy.SELF
    assert got.version == "v1"
    assert got.granted_at == 1000.0
    assert got.revoked_at is None
    assert store.get_consent(f"{ns}nope") is None


def test_invite_roundtrip_by_code(store, ns):
    store.save_invite(Invite(f"{ns}code1", f"{ns}e1", InviteRole.ELDER, 9999999999.0, 5, 0, None))
    got = store.get_invite(f"{ns}code1")
    assert got.code == f"{ns}code1"
    assert got.elder_id == f"{ns}e1"
    assert got.role == InviteRole.ELDER
    assert got.expires_at == 9999999999.0
    assert got.max_attempts == 5
    assert got.attempts == 0
    assert got.used_at is None
    assert store.get_invite(f"{ns}nope") is None
