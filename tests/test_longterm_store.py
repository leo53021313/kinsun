from kinsun.llm import Message
from kinsun.memory.longterm.store import HEALTH_QUERY, Mem0LongTermStore

# 比照 mem0 2.0.10：entity 參數（user_id/agent_id/run_id）不可走頂層 kwargs，必須用 filters。
_ENTITY_PARAMS = frozenset({"user_id", "agent_id", "run_id"})


def _reject_entity_kwargs(kwargs):
    bad = _ENTITY_PARAMS & set(kwargs)
    if bad:
        raise ValueError(
            f"Top-level entity parameters {bad} are not supported in search(). "
            "Use filters={'user_id': '...'} instead."
        )


def _texts(items):
    return [i.text for i in items]


class _FakeMem0:
    """忠實反映 mem0 2.0.10：add 用具名 user_id；search 用 filters + top_k，
    傳頂層 entity 參數一律拒絕。"""

    def __init__(self, search_return=None, raise_on_search=False):
        self.added = []
        self._search_return = search_return or {"results": []}
        self._raise = raise_on_search

    def add(self, messages, *, user_id=None, metadata=None):
        self.added.append((messages, user_id, metadata))

    def search(self, query, *, top_k=20, filters=None, **kwargs):
        _reject_entity_kwargs(kwargs)
        if self._raise:
            raise RuntimeError("boom")
        return self._search_return


class _ByQueryMem0:
    """依 query 回不同 results 的 fake；值為 "RAISE" 則該 query 拋例外。"""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def search(self, query, *, top_k=20, filters=None, **kwargs):
        _reject_entity_kwargs(kwargs)
        self.calls.append({"query": query, "top_k": top_k, "filters": filters})
        entry = self.mapping.get(query)
        if entry == "RAISE":
            raise RuntimeError("boom")
        return entry or {"results": []}


def test_add_maps_messages_and_metadata():
    mem = _FakeMem0()
    store = Mem0LongTermStore(mem)
    store.add("sess1", [Message("user", "我叫王大明")], provenance="self_claimed")
    messages, user_id, metadata = mem.added[0]
    assert messages == [{"role": "user", "content": "我叫王大明"}]
    assert user_id == "sess1"
    assert metadata == {"provenance": "self_claimed"}


def test_search_returns_memory_items():
    mem = _FakeMem0(search_return={"results": [{"memory": "喜歡下棋", "metadata": {}}]})
    items = Mem0LongTermStore(mem).search("興趣", "sess1")
    assert _texts(items) == ["喜歡下棋"]


def test_search_maps_provenance_label_and_date():
    mem = _FakeMem0(
        search_return={
            "results": [
                {
                    "memory": "有高血壓",
                    "created_at": "2026-07-04T02:30:41+00:00",
                    "metadata": {"provenance": "self_claimed"},
                }
            ]
        }
    )
    item = Mem0LongTermStore(mem).search("x", "sess1")[0]
    assert item.text == "有高血壓"
    assert item.provenance == "長者自述"
    assert item.date == "2026-07-04"


def test_search_scopes_by_user_id_via_filters():
    """search 必須用 filters={'user_id': ...} 與 top_k（mem0 2.0.10 契約），
    否則會被 mem0 拒絕、退化成無記憶。"""
    mem = _ByQueryMem0({"興趣": {"results": [{"id": "1", "memory": "喜歡下棋"}]}})
    items = Mem0LongTermStore(mem, top_k=5).search("sess1", "興趣")
    assert "喜歡下棋" in _texts(items)  # 真的檢索到，沒因 API 用錯而退化成空
    call = next(c for c in mem.calls if c["query"] == "興趣")
    assert call["filters"] == {"user_id": "sess1"}
    assert call["top_k"] == 5


def test_search_failsafe_returns_empty_list():
    store = Mem0LongTermStore(_FakeMem0(raise_on_search=True))
    assert store.search("x", "sess1") == []


def test_search_always_includes_health_facts():
    mem = _ByQueryMem0(
        {
            "今天天氣": {"results": [{"id": "1", "memory": "喜歡晴天"}]},
            HEALTH_QUERY: {"results": [{"id": "2", "memory": "有高血壓，每天吃藥"}]},
        }
    )
    items = Mem0LongTermStore(mem).search("sess1", "今天天氣")
    assert "喜歡晴天" in _texts(items)
    assert "有高血壓，每天吃藥" in _texts(items)


def test_search_dedups_overlapping_id():
    mem = _ByQueryMem0(
        {
            "頭痛": {"results": [{"id": "1", "memory": "有高血壓"}]},
            HEALTH_QUERY: {"results": [{"id": "1", "memory": "有高血壓"}]},
        }
    )
    items = Mem0LongTermStore(mem).search("sess1", "頭痛")
    assert _texts(items).count("有高血壓") == 1


def test_search_uses_top_k_and_health_top_k():
    mem = _ByQueryMem0({})
    Mem0LongTermStore(mem, top_k=5, health_top_k=2).search("sess1", "天氣")
    calls = {(c["query"], c["top_k"]) for c in mem.calls}
    assert ("天氣", 5) in calls
    assert (HEALTH_QUERY, 2) in calls


def test_health_search_failure_keeps_user_results():
    mem = _ByQueryMem0(
        {"頭痛": {"results": [{"id": "1", "memory": "今天頭痛"}]}, HEALTH_QUERY: "RAISE"}
    )
    items = Mem0LongTermStore(mem).search("sess1", "頭痛")
    assert "今天頭痛" in _texts(items)


def test_search_orders_newest_first():
    mem = _FakeMem0(
        search_return={
            "results": [
                {"id": "a", "memory": "喜歡壽司", "created_at": "2026-07-03T19:01:08+00:00"},
                {"id": "b", "memory": "喜歡麥當勞", "created_at": "2026-07-04T02:30:41+00:00"},
            ]
        }
    )
    assert _texts(Mem0LongTermStore(mem).search("sess1", "食物")) == ["喜歡麥當勞", "喜歡壽司"]


def test_search_missing_created_at_sorts_last():
    mem = _FakeMem0(
        search_return={
            "results": [
                {"id": "a", "memory": "沒日期的事實", "metadata": {"provenance": "self_claimed"}},
                {"id": "b", "memory": "喜歡麥當勞", "created_at": "2026-07-04T02:30:41+00:00"},
            ]
        }
    )
    assert _texts(Mem0LongTermStore(mem).search("sess1", "x")) == ["喜歡麥當勞", "沒日期的事實"]
