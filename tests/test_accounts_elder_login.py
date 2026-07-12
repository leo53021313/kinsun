"""長輩帳密（✅ D-71 己-6）：家屬代辦註冊＋長輩手機登入（首次一定掃碼配對，帳密只管重登）。"""

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.accounts.models import ConsentBy, InviteRole, PrincipalType
from kinsun.accounts.service import AccountService, AppAccountError
from tests.fakes import FakeAccountStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 10, 12, 0, tzinfo=TPE)


def _service(repo=None):
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    return AccountService(
        repo or FakeAccountStore(),
        clock=lambda: NOW,
        new_id=lambda: next(ids),
        new_code=lambda: next(codes),
    )


def _paired_elder(svc):
    """家屬建長輩＋長輩機掃碼配對（同意留痕＋APP 綁定）。"""
    elder = svc.create_elder("U-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.bind_elder_device(invite.code, consent_by=ConsentBy.PROXY)
    return elder


def test_register_then_login_returns_elder_token():
    svc = _service()
    elder = _paired_elder(svc)
    svc.register_elder_account(elder.elder_id, "0912-345 678", "sunsun-8888")
    got, token = svc.login_elder("0912345678", "sunsun-8888")
    assert got.elder_id == elder.elder_id
    auth = svc.authenticate_token(token)
    assert auth.principal_type is PrincipalType.ELDER
    assert auth.principal_id == elder.elder_id


def test_login_normalizes_phone_input():
    svc = _service()
    elder = _paired_elder(svc)
    svc.register_elder_account(elder.elder_id, "0912345678", "sunsun-8888")
    got, _ = svc.login_elder(" 0912-345-678 ", "sunsun-8888")
    assert got.elder_id == elder.elder_id


def test_login_wrong_password_or_unknown_phone_same_error():
    svc = _service()
    elder = _paired_elder(svc)
    svc.register_elder_account(elder.elder_id, "0912345678", "sunsun-8888")
    with pytest.raises(AppAccountError) as exc1:
        svc.login_elder("0912345678", "wrong-password")
    with pytest.raises(AppAccountError) as exc2:
        svc.login_elder("0900000000", "sunsun-8888")
    # 不洩漏帳號存在性：兩種失敗同一錯誤碼。
    assert exc1.value.reason == exc2.value.reason == "invalid_credentials"


def test_login_requires_pairing_first():
    """首次一定要掃碼配對（Leo 2026-07-10）：沒配對過打帳密 → 提示先掃碼。"""
    svc = _service()
    elder = svc.create_elder("U-son", "兒子", "阿公")  # 只建檔，未掃碼
    svc.register_elder_account(elder.elder_id, "0912345678", "sunsun-8888")
    with pytest.raises(AppAccountError) as exc:
        svc.login_elder("0912345678", "sunsun-8888")
    assert exc.value.reason == "not_paired"


def test_login_after_device_revoke_restores_app_binding():
    """帳密管「重登」：作廢裝置後（綁定＋token 全撤）帳密登入即恢復，不用跟家屬要新碼。"""
    svc = _service()
    elder = _paired_elder(svc)
    svc.register_elder_account(elder.elder_id, "0912345678", "sunsun-8888")
    svc.revoke_elder_device(elder.elder_id)
    assert svc.app_external_id_of_elder(elder.elder_id) is None
    _, token = svc.login_elder("0912345678", "sunsun-8888")
    assert svc.app_external_id_of_elder(elder.elder_id) is not None
    assert svc.authenticate_token(token).principal_id == elder.elder_id


def test_register_rejects_phone_of_another_elder():
    svc = _service()
    elder_a = _paired_elder(svc)
    elder_b = svc.create_elder_for_guardian("id1", "阿嬤")  # 同家屬第二位長輩
    svc.register_elder_account(elder_a.elder_id, "0912345678", "sunsun-8888")
    with pytest.raises(AppAccountError) as exc:
        svc.register_elder_account(elder_b.elder_id, "0912345678", "other-8888")
    assert exc.value.reason == "phone_taken"


def test_register_same_elder_resets_password():
    svc = _service()
    elder = _paired_elder(svc)
    svc.register_elder_account(elder.elder_id, "0912345678", "old-password-8")
    svc.register_elder_account(elder.elder_id, "0912345678", "new-password-8")
    got, _ = svc.login_elder("0912345678", "new-password-8")
    assert got.elder_id == elder.elder_id
    with pytest.raises(AppAccountError):
        svc.login_elder("0912345678", "old-password-8")


def test_register_rejects_bad_phone():
    svc = _service()
    elder = _paired_elder(svc)
    for bad in ("12345", "abc-defg-hij", ""):
        with pytest.raises(AppAccountError) as exc:
            svc.register_elder_account(elder.elder_id, bad, "sunsun-8888")
        assert exc.value.reason == "invalid_phone"


def test_login_binding_survives_logout():
    """登出只撤 token、APP 綁定保留；再登入不重複建綁定。"""
    svc = _service()
    elder = _paired_elder(svc)
    svc.register_elder_account(elder.elder_id, "0912345678", "sunsun-8888")
    first_external = svc.app_external_id_of_elder(elder.elder_id)
    _, token = svc.login_elder("0912345678", "sunsun-8888")
    svc.logout(token)
    svc.login_elder("0912345678", "sunsun-8888")
    assert svc.app_external_id_of_elder(elder.elder_id) == first_external
