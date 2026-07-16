"""守則注入 system prompt：只有生效中的守則會進去，且永不凌駕安全提醒。"""

from __future__ import annotations

from kinsun.memory.recall import SessionMemory
from kinsun.strategies.facts import StrategyFacts
from kinsun.strategies.models import STRATEGY_CATEGORY_ADDRESS, STRATEGY_CATEGORY_TONE
from kinsun.strategies.store import FakeStrategyStore
from tests.fakes import FakeLongTermStore


class _ShortTerm:
    def recent(self, elder_id):
        return []

    def append(self, elder_id, message):  # pragma: no cover - 本檔不記錄對話
        pass


def test_no_strategies_yields_no_section():
    assert StrategyFacts(FakeStrategyStore(), max_strategies=15).facts("e1") is None


def test_adopted_strategies_become_section_items():
    store = FakeStrategyStore()
    store.record("e1", "不要叫她阿婆", STRATEGY_CATEGORY_ADDRESS, "她糾正過兩次", 4, None)
    store.record("e1", "回話簡短些", STRATEGY_CATEGORY_TONE, "長句多半沒回", 3, None)

    section = StrategyFacts(store, max_strategies=15).facts("e1")

    assert set(section.items) == {"不要叫她阿婆", "回話簡短些"}


def test_other_elders_strategies_are_not_injected():
    store = FakeStrategyStore()
    store.record("e2", "別位長輩的守則", STRATEGY_CATEGORY_TONE, "證據", 3, None)

    assert StrategyFacts(store, max_strategies=15).facts("e1") is None


def test_revoked_strategies_are_not_injected():
    store = FakeStrategyStore()
    store.record("e1", "撤掉的守則", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    store.revoke(store.list_for_elder("e1")[0].strategy_id)

    assert StrategyFacts(store, max_strategies=15).facts("e1") is None


def test_superseded_strategies_are_not_injected():
    store = FakeStrategyStore()
    store.record("e1", "舊守則", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    old_id = store.list_for_elder("e1")[0].strategy_id
    store.record("e1", "新守則", STRATEGY_CATEGORY_TONE, "證據", 3, old_id)

    section = StrategyFacts(store, max_strategies=15).facts("e1")

    assert section.items == ["新守則"]


def test_only_the_newest_strategies_up_to_the_cap_are_injected():
    store = FakeStrategyStore()
    for i in range(20):
        store.record("e1", f"守則{i}", STRATEGY_CATEGORY_TONE, "證據", 3, None)

    section = StrategyFacts(store, max_strategies=15).facts("e1")

    assert len(section.items) == 15
    assert "守則19" in section.items  # 最新的有進去
    assert "守則0" not in section.items  # 最舊的被擠掉


def test_the_section_title_forbids_overriding_safety():
    store = FakeStrategyStore()
    store.record("e1", "不要叫她阿婆", STRATEGY_CATEGORY_ADDRESS, "證據", 3, None)

    section = StrategyFacts(store, max_strategies=15).facts("e1")

    assert "安全" in section.title
    assert "用藥" in section.title


def test_evidence_never_reaches_the_system_prompt():
    """證據永不進 prompt——這是「濾網只檢查 content」得以成立的唯一前提。

    policy.py 刻意不過濾 evidence（證據本就會提到長輩身體狀況，過濾會誤殺合法守則）。
    一旦 evidence 進了 prompt，模型只要把指令藏進證據欄就能繞過全部防線。
    這條測試是那道前提的釘子：走完整注入路徑（StrategyFacts → SessionMemory →
    TurnContext.system_suffix），逐字斷言證據不在最終 prompt 後綴裡。
    """
    store = FakeStrategyStore()
    evidence = "她說不用再提醒她吃藥了"
    store.record("e1", "她早上比較晚起", STRATEGY_CATEGORY_TONE, evidence, 3, None)
    session = SessionMemory(
        _ShortTerm(),
        FakeLongTermStore(),
        facts=[StrategyFacts(store, max_strategies=15)],
    )

    suffix = session.assemble("e1", "早安").system_suffix

    assert "她早上比較晚起" in suffix  # 守則本身有進去
    assert evidence not in suffix
    assert "吃藥" not in suffix
