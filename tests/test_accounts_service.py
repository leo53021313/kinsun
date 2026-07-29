from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.accounts.models import (
    Channel,
    ChannelBinding,
    ConsentBy,
    InviteRole,
    PrincipalType,
    Role,
)
from kinsun.accounts.service import AccountService, AppAccountError, InviteError
from tests.fakes import FakeAccountStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 6, 29, 10, 0, tzinfo=TPE)


def _service(repo, *, now=NOW):
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    return AccountService(
        repo, clock=lambda: now, new_id=lambda: next(ids), new_code=lambda: next(codes)
    )


def test_create_elder_makes_primary_guardian():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    assert elder.name == "阿公"
    eg = repo.list_elder_guardians(elder.elder_id)[0]
    assert eg.role == Role.PRIMARY
    assert eg.escalation_order == 1


def test_generate_invite_sets_ttl_and_limit():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    assert inv.role == InviteRole.ELDER
    assert inv.max_attempts == 5
    assert inv.expires_at == (NOW + timedelta(hours=24)).timestamp()
    assert repo.get_invite(inv.code) == inv


def test_redeem_elder_binds_line():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    binding = repo.get_channel_binding(Channel.LINE, "U-elder")
    assert binding is not None
    assert binding.principal_type.value == "elder"
    assert binding.principal_id == elder.elder_id
    assert repo.get_consent(elder.elder_id).consent_by == ConsentBy.SELF
    assert repo.get_invite(inv.code).used_at is not None


def test_redeem_guardian_adds_relation():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-daughter", consent_by=ConsentBy.SELF)
    egs = repo.list_elder_guardians(elder.elder_id)
    assert len(egs) == 2
    assert egs[1].role == Role.GUARDIAN
    assert egs[1].escalation_order == 2


def test_redeem_unknown_code():
    svc = _service(FakeAccountStore())
    with pytest.raises(InviteError) as exc:
        svc.redeem_invite("nope", "U-x", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "not_found"


def test_redeem_twice_is_used():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    with pytest.raises(InviteError) as exc:
        svc.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "used"


def test_redeem_expired():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    later = _service(repo, now=NOW + timedelta(hours=25))
    with pytest.raises(InviteError) as exc:
        later.redeem_invite(inv.code, "U-d", consent_by=ConsentBy.SELF)
    assert exc.value.reason == "expired"
    assert repo.get_invite(inv.code).attempts == 1


def test_guardian_redeem_does_not_create_elder_consent():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-daughter", consent_by=ConsentBy.SELF)
    # 家屬綁定不代表長輩本人同意；不應替長輩寫入同意紀錄。
    assert repo.get_consent(elder.elder_id) is None


def test_guardians_of_sorted_by_escalation_order():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    svc.redeem_invite(inv.code, "U-daughter", consent_by=ConsentBy.SELF)
    egs = svc.guardians_of(elder.elder_id)
    assert [e.escalation_order for e in egs] == [1, 2]


def test_get_elder():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    assert svc.get_elder(elder.elder_id).name == "阿公"
    assert svc.get_elder("nope") is None


def test_consented_elder_lifecycle():
    repo = FakeAccountStore()
    svc = _service(repo)
    assert svc.consented_elder_id(Channel.LINE, "U-elder") is None
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    assert svc.consented_elder_id(Channel.LINE, "U-elder") is not None


def test_consented_elder_bound_without_consent():
    from kinsun.accounts.models import Elder

    repo = FakeAccountStore()
    svc = _service(repo)
    repo.save_elder(Elder("e1", "阿公"))
    repo.save_channel_binding(
        ChannelBinding(Channel.LINE, "U-elder", PrincipalType.ELDER, "e1", 1000.0)
    )
    assert svc.consented_elder_id(Channel.LINE, "U-elder") is None


def test_preview_invite_valid_and_not_found():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    p = svc.preview_invite(inv.code)
    assert p.role == InviteRole.ELDER
    assert p.elder_name == "阿公"
    assert p.reason is None
    assert svc.preview_invite("nope") is None


def test_preview_invite_expired():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    later = _service(repo, now=NOW + timedelta(hours=25))
    assert later.preview_invite(inv.code).reason == "expired"


def test_preview_invite_used():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    assert svc.preview_invite(inv.code).reason == "used"


def test_elders_managed_by():
    repo = FakeAccountStore()
    svc = _service(repo)
    assert svc.elders_managed_by("U-son") == []
    elder = svc.create_elder("U-son", "兒子", "阿公")
    managed = svc.elders_managed_by("U-son")
    assert [e.elder_id for e in managed] == [elder.elder_id]


def test_consented_elder_id_resolves_and_rejects():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv_elder = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv_elder.code, "U-elder", consent_by=ConsentBy.SELF)
    assert svc.consented_elder_id(Channel.LINE, "U-elder") == elder.elder_id
    assert svc.consented_elder_id(Channel.LINE, "U-nobody") is None


def test_create_elder_uses_repo_transaction():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    # create_elder 同時寫 elder 與 elder_guardian，且兩者皆落地
    assert repo.get_elder(elder.elder_id).name == "阿公"
    assert repo.list_elder_guardians(elder.elder_id)[0].role.value == "primary"


# --- App 帳號（階段 2）---


def test_register_guardian_account_and_login():
    repo = FakeAccountStore()
    svc = _service(repo)
    guardian, token = svc.register_guardian_account("Son@Example.com ", "correct-horse-8", "兒子")
    assert guardian.name == "兒子"
    assert len(token) >= 32
    # email 正規化：大小寫與空白不敏感。
    same, token2 = svc.login_guardian("son@example.com", "correct-horse-8")
    assert same.guardian_id == guardian.guardian_id
    assert token2 != token  # 每次登入發新 token
    auth = svc.authenticate_token(token2)
    assert auth is not None
    assert auth.principal_type == PrincipalType.GUARDIAN
    assert auth.principal_id == guardian.guardian_id


def test_register_duplicate_email_rejected():
    repo = FakeAccountStore()
    svc = _service(repo)
    svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    with pytest.raises(AppAccountError) as exc:
        svc.register_guardian_account("SON@example.com", "other-pass-123", "路人")
    assert exc.value.reason == "email_taken"


def test_login_failures_are_indistinguishable():
    repo = FakeAccountStore()
    svc = _service(repo)
    svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    with pytest.raises(AppAccountError) as wrong_pw:
        svc.login_guardian("son@example.com", "wrong-password")
    with pytest.raises(AppAccountError) as no_user:
        svc.login_guardian("nobody@example.com", "correct-horse-8")
    assert wrong_pw.value.reason == no_user.value.reason == "invalid_credentials"


def test_bind_elder_device_issues_token_and_app_binding():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    bound, token = svc.bind_elder_device(inv.code, consent_by=ConsentBy.PROXY)
    assert bound.elder_id == elder.elder_id
    auth = svc.authenticate_token(token)
    assert auth.principal_type == PrincipalType.ELDER
    assert auth.principal_id == elder.elder_id
    # channel_bindings 應有一筆 app 綁定指向該長輩，且同意已寫入。
    bindings = repo.list_channel_bindings_for_principal(PrincipalType.ELDER, elder.elder_id)
    assert [b.channel for b in bindings] == [Channel.APP]
    assert svc.has_valid_consent(elder.elder_id) is True
    # 邀請碼一次性：再用即失敗。
    with pytest.raises(InviteError):
        svc.bind_elder_device(inv.code, consent_by=ConsentBy.PROXY)


def test_bind_elder_device_rejects_guardian_invite():
    """庚-04（A-46）：家屬邀請碼不可經 /device-bindings 換出長輩裝置 token。

    修復前 bind_elder_device 不看 invite.role，GUARDIAN 碼會走 redeem 的 guardian
    分支（建空名 Guardian＋消耗邀請碼）卻仍發長輩 token——權限邊界破口。
    """
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    guardian_invite = svc.generate_invite(elder.elder_id, InviteRole.GUARDIAN)
    with pytest.raises(InviteError) as exc:
        svc.bind_elder_device(guardian_invite.code, consent_by=ConsentBy.PROXY)
    assert exc.value.reason == "wrong_role"
    # 邀請碼未被消耗（仍可正常給家屬用）、未發任何 token、未建綁定。
    assert repo.get_invite(guardian_invite.code).used_at is None
    assert repo.list_channel_bindings_for_principal(PrincipalType.ELDER, elder.elder_id) == []


def test_logout_all_devices_revokes_every_guardian_token():
    """庚-05（A-47）：家屬「登出所有裝置」撤銷該家屬全部 token（永久 token 外洩補救）。"""
    repo = FakeAccountStore()
    svc = _service(repo)
    guardian = svc.register_guardian_account("a@example.com", "correct-horse-8", "兒子")[0]
    # 同一家屬多裝置登入 → 多顆 token。
    _, t1 = svc.login_guardian("a@example.com", "correct-horse-8")
    _, t2 = svc.login_guardian("a@example.com", "correct-horse-8")
    assert svc.authenticate_token(t1) is not None
    assert svc.authenticate_token(t2) is not None
    svc.logout_all_devices(guardian.guardian_id)
    assert svc.authenticate_token(t1) is None
    assert svc.authenticate_token(t2) is None


def test_authenticate_token_rejects_unknown():
    svc = _service(FakeAccountStore())
    assert svc.authenticate_token("not-a-real-token") is None


def test_redeem_invite_line_channel_unchanged():
    # 既有 LINE 路徑（預設 channel）不受簽名擴充影響。
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    inv = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.redeem_invite(inv.code, "U-elder", consent_by=ConsentBy.SELF)
    binding = repo.get_channel_binding(Channel.LINE, "U-elder")
    assert binding is not None and binding.principal_id == elder.elder_id


def test_register_guardian_rejects_short_password():
    """✅ 庚-20（A-50）：密碼長度檢查下沉服務層——非 HTTP 呼叫者也擋弱密碼。"""
    svc = _service(FakeAccountStore())
    with pytest.raises(AppAccountError) as exc:
        svc.register_guardian_account("son@example.com", "short-7", "兒子")
    assert exc.value.reason == "password_too_short"


# ── 邀請碼容忍前後空白（A-11，2026-07-29）─────────────────────────────


def test_redeem_invite_tolerates_surrounding_whitespace():
    """複製貼上幾乎一定會帶到空白或換行。

    碼是**家屬用 LINE／訊息傳給長輩、長輩再貼進 App** 的——這條路上帶到尾隨空白
    或換行是常態，不是例外。不 strip 的話長輩看到的是「查無此邀請碼」，而他手上
    那張碼明明是對的：他會反覆重打、最後放棄，而後台完全查不到原因。
    """
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    assert (
        svc.redeem_invite(
            f"  {invite.code}\n", "U-elder", consent_by=ConsentBy.SELF, channel=Channel.APP
        )
        == elder.elder_id
    )


def test_preview_invite_tolerates_surrounding_whitespace():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    preview = svc.preview_invite(f"\t{invite.code} ")
    assert preview is not None
    assert preview.elder_name == "阿公"


def test_bind_elder_device_tolerates_surrounding_whitespace():
    repo = FakeAccountStore()
    svc = _service(repo)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    bound, token = svc.bind_elder_device(f" {invite.code} ", consent_by=ConsentBy.PROXY)
    assert bound.elder_id == elder.elder_id
    assert token


def test_whitespace_only_code_is_still_not_found():
    """strip 之後是空的＝沒有輸入，不可意外命中任何碼。"""
    repo = FakeAccountStore()
    svc = _service(repo)
    with pytest.raises(InviteError):
        svc.redeem_invite("   ", "U-elder", consent_by=ConsentBy.SELF)
    assert svc.preview_invite("  \n ") is None
