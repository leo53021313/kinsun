"""推播扇出與失效 token 清理，以及「推播失敗不可拖累落庫」這條鐵律。

為什麼特別測「不可拖累落庫」：App 內通知是唯一保證留存的路徑。推播炸掉時若讓
例外往上冒，ChannelRouter 會把整個 App 通道記成送出失敗——訊息其實已經在庫裡，
家屬卻會在後台看到一筆假的投遞失敗，而長輩打開 App 明明看得到。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

from kinsun.accounts.models import ConsentBy, InviteRole, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.channels.app.outbound import AppOutboundChannel
from kinsun.notifications.expo_push import PushOutcome
from kinsun.notifications.push_delivery import PUSH_TITLE, PushDelivery
from kinsun.notifications.push_tokens import FakePushTokenStore
from kinsun.notifications.store import FakeAppNotificationStore
from tests.fakes import FakeAccountStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 8, 0, tzinfo=TPE)


class _SpyClient:
    def __init__(self, outcome: PushOutcome | None = None, boom: bool = False) -> None:
        self.calls: list[tuple[list[str], str, str]] = []
        self._outcome = outcome or PushOutcome(1, 0, ())
        self._boom = boom

    def send(self, tokens: list[str], title: str, body: str) -> PushOutcome:
        self.calls.append((tokens, title, body))
        if self._boom:
            raise RuntimeError("Expo 掛了")
        return self._outcome


def _service():
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    return AccountService(
        FakeAccountStore(),
        clock=lambda: NOW,
        new_id=lambda: next(ids),
        new_code=lambda: next(codes),
    )


def _bound_elder(svc) -> tuple[str, str]:
    """建長輩＋App 綁定，回 (elder_id, external_id)。"""
    guardian, _ = svc.register_guardian_account("g@example.com", "correct-horse-8", "兒子")
    elder = svc.create_elder_for_guardian(guardian.guardian_id, "王阿嬤")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.bind_elder_device(invite.code, consent_by=ConsentBy.PROXY)
    return elder.elder_id, svc.app_external_id_of_elder(elder.elder_id)


def test_pushes_to_all_devices_of_the_recipient():
    svc = _service()
    elder_id, external_id = _bound_elder(svc)
    tokens = FakePushTokenStore()
    tokens.save("tok-phone", PrincipalType.ELDER, elder_id, "android")
    tokens.save("tok-tablet", PrincipalType.ELDER, elder_id, "android")
    client = _SpyClient()

    PushDelivery(svc, tokens, client).push(external_id, "早上該吃血壓藥囉")

    assert len(client.calls) == 1
    sent_tokens, title, body = client.calls[0]
    assert set(sent_tokens) == {"tok-phone", "tok-tablet"}
    assert title == PUSH_TITLE
    assert body == "早上該吃血壓藥囉"


def test_no_registered_device_does_not_call_expo():
    svc = _service()
    _, external_id = _bound_elder(svc)
    client = _SpyClient()

    PushDelivery(svc, FakePushTokenStore(), client).push(external_id, "提醒")

    assert client.calls == []


def test_unknown_external_id_does_not_call_expo():
    svc = _service()
    client = _SpyClient()

    PushDelivery(svc, FakePushTokenStore(), client).push("不存在的通道帳號", "提醒")

    assert client.calls == []


def test_dead_token_is_removed():
    """留著失效 token 只會讓之後每次派送都白打一次。"""
    svc = _service()
    elder_id, external_id = _bound_elder(svc)
    tokens = FakePushTokenStore()
    tokens.save("tok-dead", PrincipalType.ELDER, elder_id, "android")
    tokens.save("tok-live", PrincipalType.ELDER, elder_id, "android")
    client = _SpyClient(PushOutcome(1, 1, ("tok-dead",)))

    PushDelivery(svc, tokens, client).push(external_id, "提醒")

    remaining = [r.token for r in tokens.list_for_principal(PrincipalType.ELDER, elder_id)]
    assert remaining == ["tok-live"]


def test_push_to_other_person_does_not_leak():
    """兩位長輩各有裝置：推給 A 不可送到 B 的手機。"""
    svc = _service()
    elder_a, external_a = _bound_elder(svc)
    tokens = FakePushTokenStore()
    tokens.save("tok-a", PrincipalType.ELDER, elder_a, "android")
    tokens.save("tok-b", PrincipalType.ELDER, "另一位長輩", "android")
    client = _SpyClient()

    PushDelivery(svc, tokens, client).push(external_a, "提醒")

    assert client.calls[0][0] == ["tok-a"]


# ── 出站通道：落庫優先，推播失敗不可拖累 ────────────────────────


def test_outbound_records_before_pushing():
    """順序鐵律：先落庫、後推播。"""
    svc = _service()
    elder_id, external_id = _bound_elder(svc)
    store = FakeAppNotificationStore()
    tokens = FakePushTokenStore()
    tokens.save("tok", PrincipalType.ELDER, elder_id, "android")
    seen_on_push: list[int] = []

    class _CheckingClient(_SpyClient):
        def send(self, tokens_, title, body):
            seen_on_push.append(len(store.list_for_external_ids([external_id])))
            return super().send(tokens_, title, body)

    AppOutboundChannel(store, push=PushDelivery(svc, tokens, _CheckingClient())).send_text(
        external_id, "提醒"
    )

    assert seen_on_push == [1], "推播發生時訊息必須已經在庫裡"


def test_push_failure_does_not_lose_the_notification():
    svc = _service()
    elder_id, external_id = _bound_elder(svc)
    store = FakeAppNotificationStore()
    tokens = FakePushTokenStore()
    tokens.save("tok", PrincipalType.ELDER, elder_id, "android")

    AppOutboundChannel(store, push=PushDelivery(svc, tokens, _SpyClient(boom=True))).send_text(
        external_id, "提醒"
    )

    assert [n.content for n in store.list_for_external_ids([external_id])] == ["提醒"]


def test_without_push_configured_still_records():
    """未配置推播（如精簡部署）時行為與原本完全相同。"""
    store = FakeAppNotificationStore()

    AppOutboundChannel(store).send_text("ext-1", "提醒")

    assert [n.content for n in store.list_for_external_ids(["ext-1"])] == ["提醒"]
