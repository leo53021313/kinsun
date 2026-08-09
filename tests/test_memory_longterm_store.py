import time

import pytest

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


def test_add_writes_stored_facts_to_span_io(monkeypatch):
    """寫入長期記憶的對話與出處攤在 span input，供 Opik 檢視。"""
    from kinsun import tracing

    calls: list[dict] = []
    monkeypatch.setattr(tracing, "set_current_span_io", lambda **kw: calls.append(kw))
    Mem0LongTermStore(_FakeMem0()).add(
        "sess1", [Message("user", "我叫王大明")], provenance="self_claimed"
    )
    assert calls == [
        {
            "span_input": {
                "messages": [{"role": "user", "content": "我叫王大明"}],
                "metadata": {"provenance": "self_claimed"},
            }
        }
    ]


def test_add_attaches_fact_extraction_prompt(monkeypatch):
    """mem0 寫入把抽取事實用的 prompt 註冊/連結到 trace（方案 A）。"""
    from kinsun import tracing
    from kinsun.memory.longterm import provenance as prov

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(tracing, "attach_prompt", lambda n, c: calls.append((n, c)))
    Mem0LongTermStore(_FakeMem0()).add("s1", [Message("user", "我叫王大明")])
    assert ("mem0_fact_extraction", prov.CUSTOM_FACT_EXTRACTION_PROMPT) in calls


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


class _SlowMem0:
    """每次檢索固定睡 delay 秒——用來分辨兩次檢索是排隊跑還是並行跑。"""

    def __init__(self, delay: float) -> None:
        self._delay = delay

    def search(self, query, *, top_k=20, filters=None, **kwargs):
        _reject_entity_kwargs(kwargs)
        time.sleep(self._delay)
        return {"results": [{"id": query, "memory": f"關於{query}"}]}


def test_search_runs_the_two_queries_concurrently():
    """兩次檢索必須並行（2026-07-26 延遲實測）。

    每次 `_search_raw` 都是「embedding API ＋ 向量查詢 ＋ LLM rerank」，實測合計
    約 2.3 秒；兩次排隊跑就是 4.6 秒，佔端到端延遲近三成。長輩原話與固定的健康
    增補查詢彼此無依賴，沒有理由排隊。

    只斷言結果不會發現迴歸——並行版與序列版的輸出一模一樣，故以時間釘住。
    """
    delay = 0.1
    started = time.monotonic()
    items = Mem0LongTermStore(_SlowMem0(delay)).search("sess1", "頭痛")
    elapsed = time.monotonic() - started

    assert len(items) == 2  # 長輩原話 ＋ 健康增補，兩邊都拿到
    assert elapsed < delay * 2 * 0.75, f"耗時 {elapsed:.2f}s，看起來仍是排隊查"


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


class _ListableMem0:
    """支援 get_all 的 fake（mem0 2.0.10：entity 參數走 filters）。"""

    def __init__(self, get_all_return=None, raise_on_get_all=False):
        self.get_all_calls = []
        self._return = get_all_return or {"results": []}
        self._raise = raise_on_get_all

    def get_all(self, *, filters=None, limit=50, **kwargs):
        _reject_entity_kwargs(kwargs)
        self.get_all_calls.append({"filters": filters, "limit": limit})
        if self._raise:
            raise RuntimeError("boom")
        return self._return


def test_list_for_elder_maps_and_sorts_newest_first():
    """admin 觀測（spec 2026-07-12 §3.3）：列出全部記憶，created_at 由新到舊。"""
    mem = _ListableMem0(
        get_all_return={
            "results": [
                {"memory": "喜歡下棋", "created_at": "2026-07-01T08:00:00", "metadata": {}},
                {"memory": "早餐吃稀飯", "created_at": "2026-07-10T08:00:00", "metadata": {}},
            ]
        }
    )
    items = Mem0LongTermStore(mem).list_for_elder("e1")
    assert _texts(items) == ["早餐吃稀飯", "喜歡下棋"]
    assert mem.get_all_calls == [{"filters": {"user_id": "e1"}, "limit": 50}]


def test_list_for_elder_survives_mem0_failure():
    """觀測讀取失敗不可影響服務：退化為空清單。"""
    mem = _ListableMem0(raise_on_get_all=True)
    assert Mem0LongTermStore(mem).list_for_elder("e1") == []


def test_add_records_conversation_day_in_metadata():
    """整理批次凌晨 3 點寫昨天的對話：mem0 的 created_at 記今天，與內容不同日。

    對話日只有呼叫端知道，故必須明著傳進來存進 metadata（spec 2026-07-17）。
    """
    mem = _FakeMem0()
    store = Mem0LongTermStore(mem)

    store.add("sess1", [Message("user", "昨天聊的")], occurred_on="2026-07-09")

    _, _, metadata = mem.added[0]
    assert metadata == {"provenance": "self_claimed", "occurred_on": "2026-07-09"}


def test_search_date_is_conversation_day_not_write_time():
    mem = _FakeMem0(
        search_return={
            "results": [
                {
                    "memory": "孫子週末要來",
                    "created_at": "2026-07-10T03:00:00+08:00",  # 整理批次的寫入時刻
                    "metadata": {"provenance": "self_claimed", "occurred_on": "2026-07-09"},
                }
            ]
        }
    )

    item = Mem0LongTermStore(mem).search("sess1", "孫子")[0]

    assert item.date == "2026-07-09"  # 她講這話的那天，不是系統寫檔的那天


def test_search_date_falls_back_to_created_at_for_legacy_items():
    """本功能之前寫入的記憶沒有 occurred_on，維持舊行為。

    刻意不回推「created_at 減一天」：補整理批次會在同一時刻寫入多個不同的對話日，
    減一天對它們是錯的——寧可沿用舊值（晚一天），不可換成另一個錯的值。
    """
    mem = _FakeMem0(
        search_return={
            "results": [
                {"memory": "舊記憶", "created_at": "2026-07-04T02:30:41+00:00", "metadata": {}}
            ]
        }
    )

    assert Mem0LongTermStore(mem).search("sess1", "x")[0].date == "2026-07-04"


def test_search_orders_catchup_batch_by_conversation_day():
    """停機補整理（庚-06）：多個對話日在同一批次寫入，created_at 只差幾毫秒。

    此時只有對話日能定序。prompt 明著跟模型說記憶「已由新到舊排列」，排錯＝騙它。
    """
    mem = _FakeMem0(
        search_return={
            "results": [
                {
                    "id": "a",
                    "memory": "六月26 的事",
                    "created_at": "2026-07-10T03:00:00+08:00",
                    "metadata": {"occurred_on": "2026-06-26"},
                },
                {
                    "id": "b",
                    "memory": "六月28 的事",
                    "created_at": "2026-07-10T03:00:01+08:00",
                    "metadata": {"occurred_on": "2026-06-28"},
                },
                {
                    "id": "c",
                    "memory": "六月27 的事",
                    "created_at": "2026-07-10T03:00:02+08:00",  # 寫入序與對話序刻意相反
                    "metadata": {"occurred_on": "2026-06-27"},
                },
            ]
        }
    )

    items = Mem0LongTermStore(mem).search("sess1", "x")

    assert [i.date for i in items] == ["2026-06-28", "2026-06-27", "2026-06-26"]


def test_search_raw_wrapped_with_span(monkeypatch):
    """逐路檢索各成一顆 span（2026-07-30 spec）：input 的 query 分辨原話／健康路，
    output 關（合併結果已由外層 mem0_search 捕捉）。"""
    import opik

    from kinsun.tracing import client as tracing_client
    from kinsun.tracing import decorators as tracing_decorators

    tracing_client.reset_for_test()
    seen: list[dict] = []
    monkeypatch.setattr(opik, "track", lambda **kw: (seen.append(kw), lambda f: f)[1])
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)
    store = Mem0LongTermStore(_FakeMem0(search_return={"results": [{"memory": "m"}]}))
    assert _texts(store.search("elder-1", "查詢")) == ["m"]
    raw_spans = [kw for kw in seen if kw["name"] == "mem0_search_raw"]
    assert raw_spans and raw_spans[0]["capture_output"] is False


def test_health_query_does_not_trigger_mem0_entity_boost():
    """`HEALTH_QUERY` 不可被 mem0 判定含實體——那會每輪白花約 1 秒（2026-08-07 實測）。

    mem0 的 `_search_vector_store` 對抽得出實體的查詢會多跑一輪
    `_compute_entity_boosts`：先 `embed_batch` 打一次 Gemini，再對 entity store
    發 `top_k=500` 的向量查詢。實測長輩原話那路 839ms、`HEALTH_QUERY` 那路 1808ms，
    差額 994ms 全在這裡；兩路並行故總耗時由慢的那路決定。

    根因是**空格分隔**：`extract_entities("用藥 慢性病 過敏 回診 健康狀況")` 會回
    `[('TOPIC', '用藥 慢性病 過敏'), ('PROPER', '慢性病 過敏')]`，而真正的長輩口語
    （「我今天早上血壓有點高欸」）一律回 `[]`。改成頓號／自然句即不觸發，實測
    1466ms → 701ms 且撈回的記憶完全相同。

    這個成本在功能上完全看不出來（結果一樣、只是慢），沒有測試守著就會無聲回歸。
    """
    pytest.importorskip("mem0.utils.entity_extraction")
    from mem0.utils.entity_extraction import extract_entities

    assert extract_entities(HEALTH_QUERY) == [], (
        f"HEALTH_QUERY={HEALTH_QUERY!r} 被 mem0 抽出實體，每輪會多花約 1 秒；"
        "請避免以空格分隔關鍵字，改用頓號或自然句。"
    )
