"""邀請碼並發 redeem 整合測試（✅ 庚-19／A-49）：FOR UPDATE 列鎖根治 TOCTOU。

需 `KINSUN_IT=1`＋`KINSUN_TEST_DATABASE_URL`（連獨立測試庫）。離線 skip。
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

from kinsun.accounts.models import Channel, ConsentBy, InviteRole, PrincipalType
from kinsun.accounts.service import AccountService, InviteError
from kinsun.accounts.store import PgAccountStore

TPE = timezone(timedelta(hours=8))


def _service(repo):
    return AccountService(
        repo,
        clock=lambda: datetime.now(TPE),
        new_id=lambda: uuid.uuid4().hex,
        new_code=lambda: uuid.uuid4().hex[:8],
    )


def test_concurrent_redeem_same_code_binds_exactly_once(pg_database, ns):
    """兩個請求同時兌換同一個碼（長輩手滑連按／兩機同掃 QR）：
    恰一個成功、另一個收到 used；只留一筆 App 綁定。"""
    repo = PgAccountStore(pg_database)
    svc = _service(repo)
    elder = svc.create_elder(f"{ns}line-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)

    barrier = threading.Barrier(2)
    results: list[str] = []

    def attempt(n: int) -> None:
        barrier.wait()
        try:
            svc.redeem_invite(
                invite.code, f"{ns}dev{n}", channel=Channel.APP, consent_by=ConsentBy.PROXY
            )
            results.append("ok")
        except InviteError as exc:
            results.append(exc.reason)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results) == ["ok", "used"]
    app_bindings = [
        b
        for b in repo.list_channel_bindings_for_principal(PrincipalType.ELDER, elder.elder_id)
        if b.channel is Channel.APP
    ]
    assert len(app_bindings) == 1  # 僅勝者綁定成功
