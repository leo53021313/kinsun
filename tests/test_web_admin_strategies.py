"""後台守則檢視與撤銷：角色是事後撤銷（opt-out），不是事前批准。

守則由每晚反思自動生效、無人審佇列，故後台不提供「採用」動作——這裡只是逃生口：
守則學歪了要能立刻撤掉，而不必等下次部署。

撤銷端點必須據實回報是否真的命中，否則 UI 會對著一條沒撤到的守則顯示「已撤銷」。命中
判準來自 `StrategyStore.revoke()` 的回傳值（條件式 UPDATE 自己回報有沒有撤到），**不是**
先查一次 adopted 清單——那兩步之間有 TOCTOU 窗口，夜間反思剛好 commit 一個 supersede
就會讓端點謊報成功（見 `test_revoke_404_when_the_strategy_slips_away_before_the_update`）。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.strategies.models import (
    STRATEGY_CATEGORY_ADDRESS,
    STRATEGY_CATEGORY_TONE,
    STRATEGY_STATUS_ADOPTED,
    STRATEGY_STATUS_REVOKED,
)
from kinsun.strategies.store import FakeStrategyStore
from kinsun.web.envelope import install_error_envelope
from kinsun.web.routers import create_admin_strategies_router


def _client(strategies: FakeStrategyStore, *, admin_api_key: str = "secret") -> TestClient:
    app = FastAPI()
    install_error_envelope(app)  # 測試斷言 error.code 需要信封改寫
    app.include_router(
        create_admin_strategies_router(admin_api_key=admin_api_key, strategies=strategies),
        prefix="/api/v1/admin",
    )
    return TestClient(app)


def _auth():
    return {"X-Admin-Key": "secret"}


def test_list_returns_adopted_strategies_with_evidence():
    """回傳帶 evidence／observed_days：要判斷一條守則該不該撤，得看得到金孫憑什麼學到它。"""
    strategies = FakeStrategyStore()
    strategies.record("e1", "不要叫她阿婆", STRATEGY_CATEGORY_ADDRESS, "她糾正過兩次", 4, None)

    res = _client(strategies).get("/api/v1/admin/strategies?status=adopted", headers=_auth())

    assert res.status_code == 200
    items = res.json()["data"]
    assert [i["content"] for i in items] == ["不要叫她阿婆"]
    assert items[0]["elder_id"] == "e1"
    assert items[0]["category"] == STRATEGY_CATEGORY_ADDRESS
    assert items[0]["evidence"] == "她糾正過兩次"
    assert items[0]["observed_days"] == 4
    assert items[0]["status"] == STRATEGY_STATUS_ADOPTED


def test_list_spans_all_elders():
    """後台清單是跨長輩的（list_for_status），不是單一長輩視角。"""
    strategies = FakeStrategyStore()
    strategies.record("e1", "阿公的守則", STRATEGY_CATEGORY_ADDRESS, "證據", 3, None)
    strategies.record("e2", "阿嬤的守則", STRATEGY_CATEGORY_TONE, "證據", 3, None)

    res = _client(strategies).get("/api/v1/admin/strategies", headers=_auth())

    assert res.status_code == 200
    assert {i["elder_id"] for i in res.json()["data"]} == {"e1", "e2"}


def test_list_rejects_unknown_status():
    res = _client(FakeStrategyStore()).get(
        "/api/v1/admin/strategies?status=pending", headers=_auth()
    )

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_status"


def test_revoke_takes_a_strategy_out_of_effect():
    strategies = FakeStrategyStore()
    strategies.record("e1", "要撤掉的", STRATEGY_CATEGORY_ADDRESS, "證據", 3, None)
    target = strategies.list_for_elder("e1")[0]

    res = _client(strategies).patch(
        f"/api/v1/admin/strategies/{target.strategy_id}",
        json={"action": "revoke"},
        headers=_auth(),
    )

    assert res.status_code == 200
    assert res.json()["data"] == {
        "strategy_id": target.strategy_id,
        "status": STRATEGY_STATUS_REVOKED,
    }
    assert strategies.list_for_elder("e1", status=STRATEGY_STATUS_ADOPTED) == []
    assert len(strategies.list_for_elder("e1", status=STRATEGY_STATUS_REVOKED)) == 1


class SlipsAwayStore(FakeStrategyStore):
    """守則在端點按下撤銷的那一瞬間被夜間反思 supersede 掉：清單仍看得到、卻撤不到。

    復現舊版「先查 adopted 再撤」的窗口：`list_for_status` 照樣把它算成生效中，`revoke`
    卻撲空。端點若拿清單當命中判準就會回 200 謊報「已撤銷」，而那條學歪守則的改寫版正
    在生效。命中判準必須是 revoke() 的回傳值。
    """

    def revoke(self, strategy_id: str) -> bool:
        return False


def test_revoke_404_when_the_strategy_slips_away_before_the_update():
    strategies = SlipsAwayStore()
    strategies.record("e1", "學歪的守則", STRATEGY_CATEGORY_ADDRESS, "證據", 3, None)
    target = strategies.list_for_elder("e1")[0]

    res = _client(strategies).patch(
        f"/api/v1/admin/strategies/{target.strategy_id}",
        json={"action": "revoke"},
        headers=_auth(),
    )

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "strategy_not_found"


def test_revoke_unknown_strategy_404():
    """撤不到就是 404：revoke() 回 False，端點不得謊報「已撤銷」。"""
    res = _client(FakeStrategyStore()).patch(
        "/api/v1/admin/strategies/nope", json={"action": "revoke"}, headers=_auth()
    )

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "strategy_not_found"


def test_revoke_already_revoked_strategy_404():
    """已撤銷的守則不在生效中，再撤一次不是成功——否則 UI 會誤報。"""
    strategies = FakeStrategyStore()
    strategies.record("e1", "已撤掉的", STRATEGY_CATEGORY_ADDRESS, "證據", 3, None)
    target = strategies.list_for_elder("e1")[0]
    strategies.revoke(target.strategy_id)

    res = _client(strategies).patch(
        f"/api/v1/admin/strategies/{target.strategy_id}",
        json={"action": "revoke"},
        headers=_auth(),
    )

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "strategy_not_found"


def test_adopt_action_is_rejected():
    """後台不提供「採用」——沒有待審佇列，守則是自動生效的。"""
    strategies = FakeStrategyStore()
    strategies.record("e1", "守則", STRATEGY_CATEGORY_ADDRESS, "證據", 3, None)
    target = strategies.list_for_elder("e1")[0]

    res = _client(strategies).patch(
        f"/api/v1/admin/strategies/{target.strategy_id}",
        json={"action": "adopt"},
        headers=_auth(),
    )

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_action"
    assert strategies.list_for_elder("e1", status=STRATEGY_STATUS_ADOPTED) != []


def test_admin_key_is_required():
    strategies = FakeStrategyStore()
    strategies.record("e1", "守則", STRATEGY_CATEGORY_ADDRESS, "證據", 3, None)
    client = _client(strategies)

    assert client.get("/api/v1/admin/strategies").status_code == 401
    assert client.patch("/api/v1/admin/strategies/s0", json={"action": "revoke"}).status_code == 401
    # 未帶金鑰時不得有任何副作用。
    assert strategies.list_for_elder("e1", status=STRATEGY_STATUS_ADOPTED) != []
