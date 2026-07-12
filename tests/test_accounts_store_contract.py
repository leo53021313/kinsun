"""AccountStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員」關係斷言而互不干擾。

不涵蓋 transaction() 回滾：FakeAccountStore 的 `transaction()` 為 no-op（不落實
回滾語意），交易行為不在本合約範圍。所有方法皆以 `tx=None` 呼叫（兩個 adapter 皆支援）。
"""

from __future__ import annotations

import pytest

from kinsun.accounts.models import (
    ApiToken,
    Channel,
    ChannelBinding,
    Consent,
    ConsentBy,
    Elder,
    ElderAccount,
    ElderGuardian,
    Guardian,
    GuardianAccount,
    Invite,
    InviteRole,
    PrincipalType,
    Role,
)
from kinsun.accounts.store import FakeAccountStore, PgAccountStore


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgAccountStore(request.getfixturevalue("pg_database"))
    return FakeAccountStore()


def test_elder_roundtrip_and_by_line(store, ns):
    store.save_elder(Elder(f"{ns}e1", "阿公"))
    store.save_channel_binding(
        ChannelBinding(Channel.LINE, f"{ns}U-elder", PrincipalType.ELDER, f"{ns}e1", 1000.0)
    )
    got = store.get_elder(f"{ns}e1")
    assert got.name == "阿公"
    assert store.get_elder_by_line(f"{ns}U-elder").elder_id == f"{ns}e1"
    assert store.get_elder_by_line(f"{ns}nope") is None


def test_guardian_roundtrip_and_by_line(store, ns):
    store.save_guardian(Guardian(f"{ns}g1", "女兒"))
    store.save_channel_binding(
        ChannelBinding(Channel.LINE, f"{ns}U-guard", PrincipalType.GUARDIAN, f"{ns}g1", 1000.0)
    )
    assert store.get_guardian(f"{ns}g1").name == "女兒"
    assert store.get_guardian(f"{ns}nope") is None
    by_line = store.get_guardian_by_line(f"{ns}U-guard")
    assert by_line.guardian_id == f"{ns}g1"
    assert by_line.name == "女兒"


def test_elder_guardians_ordered_by_escalation(store, ns):
    elder_id = f"{ns}e1"
    # 存入順序刻意與 escalation_order 相反，證明回傳依 escalation_order 排序而非存入順序。
    store.save_elder_guardian(ElderGuardian(elder_id, f"{ns}g2", Role.GUARDIAN, 2))
    store.save_elder_guardian(ElderGuardian(elder_id, f"{ns}g1", Role.PRIMARY, 1))
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


def test_channel_binding_roundtrip_and_upsert_keeps_created_at(store, ns):
    store.save_channel_binding(
        ChannelBinding(Channel.LINE, f"{ns}U1", PrincipalType.ELDER, f"{ns}e1", 1000.0)
    )
    got = store.get_channel_binding(Channel.LINE, f"{ns}U1")
    assert got.principal_type == PrincipalType.ELDER
    assert got.principal_id == f"{ns}e1"
    assert got.created_at == 1000.0
    # upsert：改指到別的本人，但 created_at 保留首次綁定時間。
    store.save_channel_binding(
        ChannelBinding(Channel.LINE, f"{ns}U1", PrincipalType.GUARDIAN, f"{ns}g1", 2000.0)
    )
    got = store.get_channel_binding(Channel.LINE, f"{ns}U1")
    assert got.principal_type == PrincipalType.GUARDIAN
    assert got.principal_id == f"{ns}g1"
    assert got.created_at == 1000.0
    assert store.get_channel_binding(Channel.LINE, f"{ns}nope") is None


def test_channel_bindings_listed_by_principal(store, ns):
    # 同一位長輩兩個通道綁定；另一人的綁定不得混入。
    store.save_channel_binding(
        ChannelBinding(Channel.LINE, f"{ns}U-line", PrincipalType.ELDER, f"{ns}e1", 1000.0)
    )
    store.save_channel_binding(
        ChannelBinding(Channel.APP, f"{ns}dev-1", PrincipalType.ELDER, f"{ns}e1", 1100.0)
    )
    store.save_channel_binding(
        ChannelBinding(Channel.LINE, f"{ns}U-other", PrincipalType.ELDER, f"{ns}e2", 1200.0)
    )
    got = store.list_channel_bindings_for_principal(PrincipalType.ELDER, f"{ns}e1")
    assert [(b.channel, b.external_id) for b in got] == [
        (Channel.APP, f"{ns}dev-1"),
        (Channel.LINE, f"{ns}U-line"),
    ]
    assert store.list_channel_bindings_for_principal(PrincipalType.GUARDIAN, f"{ns}e1") == []


def test_guardian_account_roundtrip_by_email(store, ns):
    store.save_guardian_account(
        GuardianAccount(f"{ns}g1", f"{ns}son@example.com", "scrypt$16384$8$1$00$00", 1000.0)
    )
    got = store.get_guardian_account_by_email(f"{ns}son@example.com")
    assert got is not None
    assert got.guardian_id == f"{ns}g1"
    assert got.password_hash == "scrypt$16384$8$1$00$00"
    assert got.created_at == 1000.0
    assert store.get_guardian_account_by_email(f"{ns}nope@example.com") is None
    # upsert：同 guardian_id 換密碼雜湊。
    store.save_guardian_account(
        GuardianAccount(f"{ns}g1", f"{ns}son@example.com", "scrypt$16384$8$1$11$11", 2000.0)
    )
    assert store.get_guardian_account_by_email(f"{ns}son@example.com").password_hash == (
        "scrypt$16384$8$1$11$11"
    )


def test_elder_account_roundtrip_by_phone(store, ns):
    """✅ D-71（己-6）：長輩帳號以手機號碼為帳號；save 為 upsert（家屬可重設密碼／換號碼）。"""
    store.save_elder_account(
        ElderAccount(f"{ns}e1", f"{ns}0912345678", "scrypt$16384$8$1$00$00", 1000.0)
    )
    got = store.get_elder_account_by_phone(f"{ns}0912345678")
    assert got is not None
    assert got.elder_id == f"{ns}e1"
    assert got.password_hash == "scrypt$16384$8$1$00$00"
    assert store.get_elder_account_by_phone(f"{ns}0900000000") is None
    # upsert：同長輩重設密碼＋換手機號碼，舊號碼查不到。
    store.save_elder_account(
        ElderAccount(f"{ns}e1", f"{ns}0987654321", "scrypt$16384$8$1$11$11", 2000.0)
    )
    assert store.get_elder_account_by_phone(f"{ns}0912345678") is None
    assert store.get_elder_account_by_phone(f"{ns}0987654321").password_hash == (
        "scrypt$16384$8$1$11$11"
    )


def test_api_token_roundtrip(store, ns):
    store.save_api_token(ApiToken(f"{ns}hash1", PrincipalType.GUARDIAN, f"{ns}g1", 1000.0))
    got = store.get_api_token(f"{ns}hash1")
    assert got is not None
    assert got.principal_type == PrincipalType.GUARDIAN
    assert got.principal_id == f"{ns}g1"
    assert store.get_api_token(f"{ns}nope") is None


def test_remove_api_token_revokes_single(store, ns):
    """✅ D-25 修訂（乙-3）：登出＝撤銷單一 token。"""
    store.save_api_token(ApiToken(f"{ns}h1", PrincipalType.GUARDIAN, f"{ns}g1", 1000.0))
    store.save_api_token(ApiToken(f"{ns}h2", PrincipalType.GUARDIAN, f"{ns}g1", 1000.0))
    store.remove_api_token(f"{ns}h1")
    assert store.get_api_token(f"{ns}h1") is None
    assert store.get_api_token(f"{ns}h2") is not None


def test_remove_api_tokens_for_principal_revokes_all(store, ns):
    """✅ D-25 修訂（乙-3）：裝置作廢＝撤銷本人全部 token，不波及他人。"""
    store.save_api_token(ApiToken(f"{ns}h1", PrincipalType.ELDER, f"{ns}e1", 1000.0))
    store.save_api_token(ApiToken(f"{ns}h2", PrincipalType.ELDER, f"{ns}e1", 1000.0))
    store.save_api_token(ApiToken(f"{ns}h3", PrincipalType.ELDER, f"{ns}e2", 1000.0))
    store.remove_api_tokens_for_principal(PrincipalType.ELDER, f"{ns}e1")
    assert store.get_api_token(f"{ns}h1") is None
    assert store.get_api_token(f"{ns}h2") is None
    assert store.get_api_token(f"{ns}h3") is not None


def test_remove_channel_bindings_for_principal_scoped_by_channel(store, ns):
    """✅ D-25 修訂（乙-3）：作廢只拆 App 通道綁定，LINE 綁定不動。"""
    store.save_channel_binding(
        ChannelBinding(Channel.APP, f"{ns}ext1", PrincipalType.ELDER, f"{ns}e1", 1000.0)
    )
    store.save_channel_binding(
        ChannelBinding(Channel.LINE, f"{ns}U1", PrincipalType.ELDER, f"{ns}e1", 1000.0)
    )
    store.remove_channel_bindings_for_principal(Channel.APP, PrincipalType.ELDER, f"{ns}e1")
    channels = {
        b.channel for b in store.list_channel_bindings_for_principal(PrincipalType.ELDER, f"{ns}e1")
    }
    assert Channel.APP not in channels
    assert Channel.LINE in channels


def test_list_invites_for_elder_filters_and_sorts(store, ns):
    """admin 觀測（spec 2026-07-12 §3.3）：只回該長輩的邀請碼，expires_at 由新到舊。"""
    store.save_invite(Invite(f"{ns}c1", f"{ns}e1", InviteRole.ELDER, 1000.0, 5, 0, None))
    store.save_invite(Invite(f"{ns}c2", f"{ns}e1", InviteRole.GUARDIAN, 2000.0, 5, 0, None))
    store.save_invite(Invite(f"{ns}c9", f"{ns}e2", InviteRole.ELDER, 3000.0, 5, 0, None))
    codes = [i.code for i in store.list_invites_for_elder(f"{ns}e1")]
    assert codes == [f"{ns}c2", f"{ns}c1"]
    assert store.list_invites_for_elder(f"{ns}nobody") == []


def test_list_api_tokens_for_principal_filters_and_sorts(store, ns):
    """admin 觀測（spec 2026-07-12 §3.3）：只回本人 token 概況，created_at 由新到舊。"""
    store.save_api_token(ApiToken(f"{ns}h1", PrincipalType.ELDER, f"{ns}e1", 1000.0))
    store.save_api_token(ApiToken(f"{ns}h2", PrincipalType.ELDER, f"{ns}e1", 2000.0))
    store.save_api_token(ApiToken(f"{ns}h3", PrincipalType.GUARDIAN, f"{ns}g1", 3000.0))
    hashes = [t.token_hash for t in store.list_api_tokens_for_principal(PrincipalType.ELDER, f"{ns}e1")]
    assert hashes == [f"{ns}h2", f"{ns}h1"]
    assert store.list_api_tokens_for_principal(PrincipalType.ELDER, f"{ns}nobody") == []


def test_get_elder_account_by_elder_id(store, ns):
    """admin 觀測（spec 2026-07-12 §3.3）：以 elder_id 查長輩帳號有無設定。"""
    store.save_elder_account(
        ElderAccount(f"{ns}e1", f"{ns}0912345678", "scrypt$16384$8$1$00$00", 1000.0)
    )
    got = store.get_elder_account(f"{ns}e1")
    assert got is not None
    assert got.phone == f"{ns}0912345678"
    assert store.get_elder_account(f"{ns}nobody") is None
