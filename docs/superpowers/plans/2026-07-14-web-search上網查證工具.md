# web_search 上網查證工具 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓金孫（CareAgent）多一個 `web_search` 工具，能依主題（時事／衛教備援／謠言查證）帶不同網域白名單上網查證，並把完整來源落庫留痕。

**Architecture:** 仿既有 `weather.py` 的「`ToolSpec` 常數＋`build_*_handler` 工廠＋注入 `Transport`」模式新增 `tools/web_search.py`；來源紀錄走既有持久層三件套（`tools/lookups.py`：Protocol＋Pg＋Fake），DDL 進 `db.py` 的 `ensure_schema`。搜尋後端 Tavily，經既有 `kinsun.transport` 呼叫，**不新增第三方套件**。金鑰未設時 `build_tool_registry` 跳過註冊，系統優雅降級。

**Tech Stack:** Python 3、既有 `kinsun.transport`（urllib）、Postgres（psycopg）、pytest、Tavily Search API。

## Global Constraints

- 設計來源：`docs/superpowers/specs/2026-07-14-web-search上網查證工具-design.md`（已由 Leo 核可）。
- 不新增第三方依賴套件；HTTP 一律走 `kinsun.transport` 的 `Transport`（可注入，測試用 `FakeTransport`）。
- 命名遵守 AGENTS.md：ID 全稱 `web_search_lookup_id`；時間戳 `created_at`，型別 `DOUBLE PRECISION`（epoch 秒）；append-only 寫入動詞用 `record`；持久層三件套（Protocol／`Pg*`／`Fake*` 同住一檔）。
- 環境變數 `TAVILY_API_KEY`，`Settings` 欄位 `tavily_api_key`（一一對應、預設空字串），必須列進 `.env.example` 並附中文註解。
- 工具永不拋例外中斷對話；來源落庫失敗只留 warning，不影響回覆。
- 所有註解與 commit 訊息用台灣繁體中文。
- 測試檔名：`tests/test_tools_web_search.py`、`tests/test_web_search_store_contract.py`。合約測試同一份斷言參數化跑 Fake（每次跑）與 Pg（`KINSUN_IT=1` 才跑）。
- DDL 順序固定：建表 → 遷移 → 建索引（本表為新表，無遷移段）。

## File Structure

| 檔案 | 責任 |
| :--- | :--- |
| `src/kinsun/tools/lookups.py`（新增） | 上網查證來源紀錄持久層三件套（`WebSearchLookupStore` Protocol、`PgWebSearchLookupStore`、`FakeWebSearchLookupStore`）＋`WebSearchLookup` 模型＋狀態常數。 |
| `src/kinsun/tools/web_search.py`（新增） | `WEB_SEARCH_SPEC`、分主題白名單常數表、`build_web_search_handler`（呼叫 Tavily、格式化結果、落庫）。 |
| `src/kinsun/db.py`（修改） | 新增 `WEB_SEARCH_LOOKUPS_DDL`，在 `ensure_schema` 執行。 |
| `src/kinsun/config.py`（修改） | `Settings.tavily_api_key` 欄位＋`load_settings` 讀 `TAVILY_API_KEY`。 |
| `src/kinsun/composition.py`（修改） | `build_tool_registry` 收金鑰與 lookup store，有金鑰才註冊 `web_search`；`assemble_core` 建 `PgWebSearchLookupStore` 並傳入。 |
| `src/kinsun/agent.py`（修改） | `SYSTEM_PROMPT` 增訂上網查證與來源口語化規則。 |
| `.env.example`（修改） | 新增 `TAVILY_API_KEY` 與中文註解。 |
| `tests/test_tools_web_search.py`（新增） | 工具離線測試（注入 `FakeTransport`＋`FakeWebSearchLookupStore`）。 |
| `tests/test_web_search_store_contract.py`（新增） | Fake／Pg 等價合約測試。 |
| `tests/test_composition.py`（修改） | 補「無金鑰不註冊／有金鑰註冊第四個工具」守門測試。 |
| `tests/test_config.py`（修改） | 補 `tavily_api_key` 預設空字串與讀值測試。 |

---

### Task 1: 來源紀錄持久層（三件套＋DDL）

**Files:**
- Create: `src/kinsun/tools/lookups.py`
- Modify: `src/kinsun/db.py`（DDL 常數區＋`ensure_schema`）
- Test: `tests/test_web_search_store_contract.py`

**Interfaces:**
- Produces（Task 2、3 會用到）：
  - `WebSearchLookupStore` Protocol：`record(*, query: str, topic: str, status: str, sources: list[dict]) -> None`、`list_recent(limit: int = 50) -> list[WebSearchLookup]`
  - `PgWebSearchLookupStore(db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str])`
  - `FakeWebSearchLookupStore()`，公開屬性 `recorded: list[tuple[str, str, str, list[dict]]]`
  - 狀態常數 `STATUS_OK = "ok"`、`STATUS_EMPTY = "empty"`、`STATUS_ERROR = "error"`
  - `WebSearchLookup` dataclass：`web_search_lookup_id`、`query`、`topic`、`status`、`sources`、`created_at`

- [ ] **Step 1: 寫失敗的合約測試** — `tests/test_web_search_store_contract.py`

```python
"""WebSearchLookupStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連獨立測試庫）。斷言以 `ns` 前綴 scope 到本測試
自己的 query，才能在共用測試庫上互不干擾。
"""

from __future__ import annotations

import itertools
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kinsun.tools.lookups import (
    STATUS_EMPTY,
    STATUS_OK,
    FakeWebSearchLookupStore,
    PgWebSearchLookupStore,
)

_SOURCES = [{"title": "颱風假公告", "site": "cdc.gov.tw", "url": "https://cdc.gov.tw/a"}]


def _counter_clock():
    """單調遞增時鐘：讓 Pg 的 created_at 排序可預期，對齊 Fake 的附加順序。"""
    ticks = itertools.count(1)
    return lambda: datetime.fromtimestamp(next(ticks), tz=ZoneInfo("Asia/Taipei"))


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        ids = itertools.count(1)
        return PgWebSearchLookupStore(
            request.getfixturevalue("pg_database"),
            clock=_counter_clock(),
            new_id=lambda: f"wsl-{next(ids)}-{request.node.name}",
        )
    return FakeWebSearchLookupStore()


def _mine(store, ns):
    return [lookup for lookup in store.list_recent(limit=50) if lookup.query.startswith(ns)]


def test_list_recent_empty_before_record(store, ns):
    assert _mine(store, ns) == []


def test_record_then_list_round_trips(store, ns):
    store.record(query=f"{ns}颱風假", topic="general", status=STATUS_OK, sources=_SOURCES)
    got = _mine(store, ns)
    assert len(got) == 1
    assert got[0].query == f"{ns}颱風假"
    assert got[0].topic == "general"
    assert got[0].status == STATUS_OK
    assert got[0].sources == _SOURCES


def test_record_empty_sources_round_trips(store, ns):
    store.record(query=f"{ns}查無", topic="rumor_check", status=STATUS_EMPTY, sources=[])
    got = _mine(store, ns)
    assert len(got) == 1
    assert got[0].status == STATUS_EMPTY
    assert got[0].sources == []


def test_list_recent_orders_newest_first(store, ns):
    store.record(query=f"{ns}舊", topic="general", status=STATUS_OK, sources=[])
    store.record(query=f"{ns}新", topic="general", status=STATUS_OK, sources=[])
    assert [lookup.query for lookup in _mine(store, ns)] == [f"{ns}新", f"{ns}舊"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_web_search_store_contract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kinsun.tools.lookups'`

- [ ] **Step 3: 寫最小實作** — `src/kinsun/tools/lookups.py`

```python
"""上網查證來源紀錄持久化：append-only 流水帳，供日後追查金孫引用了哪些網頁。

金孫回覆長輩時只會口語帶一句來源（「衛福部網站說…」），完整網址不唸出來；
本表把每次查詢的關鍵字、主題與來源清單留痕，日後要查證引用出處時看這裡。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from psycopg.types.json import Json

from kinsun.db import Database, _Errors

logger = logging.getLogger("kinsun.tools.lookups")

# 查詢結果狀態：ok＝有結果、empty＝白名單內查無、error＝搜尋服務失敗。
STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class WebSearchLookup:
    web_search_lookup_id: str
    query: str
    topic: str
    status: str
    sources: list[dict]
    created_at: float


class WebSearchLookupError(Exception):
    """上網查證紀錄讀寫失敗。"""


class WebSearchLookupStore(Protocol):
    def record(self, *, query: str, topic: str, status: str, sources: list[dict]) -> None: ...
    def list_recent(self, limit: int = 50) -> list[WebSearchLookup]: ...


class PgWebSearchLookupStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: WebSearchLookupError(f"上網查證紀錄存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(self, *, query: str, topic: str, status: str, sources: list[dict]) -> None:
        self._db.execute(
            "INSERT INTO web_search_lookups "
            "(web_search_lookup_id, query, topic, status, sources, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                query,
                topic,
                status,
                Json(sources),
                self._clock().timestamp(),
            ),
        )

    def list_recent(self, limit: int = 50) -> list[WebSearchLookup]:
        rows = self._db.query(
            "SELECT web_search_lookup_id, query, topic, status, sources, created_at "
            "FROM web_search_lookups ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        return [WebSearchLookup(*row) for row in rows]


class FakeWebSearchLookupStore:
    """WebSearchLookupStore 的記憶體替身（測試用，不碰 DB）。

    web_search_lookup_id 與 created_at 由附加順序虛構、僅供排序，因此合約只斷言雙方
    都會產生的欄位。回傳由新到舊，對齊 PgWebSearchLookupStore 的 ORDER BY DESC。
    """

    def __init__(self) -> None:
        self.recorded: list[tuple[str, str, str, list[dict]]] = []

    def record(self, *, query: str, topic: str, status: str, sources: list[dict]) -> None:
        self.recorded.append((query, topic, status, list(sources)))

    def list_recent(self, limit: int = 50) -> list[WebSearchLookup]:
        lookups = [
            WebSearchLookup(str(i), query, topic, status, sources, float(i))
            for i, (query, topic, status, sources) in enumerate(self.recorded)
        ]
        return sorted(lookups, key=lambda lookup: lookup.created_at, reverse=True)[:limit]


def safe_record(
    lookups: WebSearchLookupStore | None,
    *,
    query: str,
    topic: str,
    status: str,
    sources: list[dict],
) -> None:
    """留痕失敗絕不中斷對話：吞掉所有例外、只留 warning。"""
    if lookups is None:
        return
    try:
        lookups.record(query=query, topic=topic, status=status, sources=sources)
    except Exception:  # noqa: BLE001 - 觀測記錄失敗不可影響主流程
        logger.warning("上網查證紀錄落庫失敗", exc_info=True)
```

- [ ] **Step 4: 加 DDL** — `src/kinsun/db.py`

在 `APP_NOTIFICATIONS_DDL` 常數之後新增：

```python
# 上網查證來源紀錄（spec 2026-07-14）：金孫每次 web_search 的關鍵字、主題與來源清單。
# 新表、無遷移段；索引與建表同批（既有庫首次跑時一起建）。
WEB_SEARCH_LOOKUPS_DDL = (
    "CREATE TABLE IF NOT EXISTS web_search_lookups ("
    "web_search_lookup_id TEXT PRIMARY KEY, query TEXT NOT NULL, topic TEXT NOT NULL, "
    "status TEXT NOT NULL, sources JSONB NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_web_search_lookups_created "
    "ON web_search_lookups (created_at);"
)
```

在 `ensure_schema` 的 `conn.execute(APP_NOTIFICATIONS_DDL)` 之後加一行：

```python
        conn.execute(WEB_SEARCH_LOOKUPS_DDL)
```

- [ ] **Step 5: 跑測試確認通過**

Run: `uv run pytest tests/test_web_search_store_contract.py -v`
Expected: PASS（Fake 全過；`KINSUN_IT=1` 時 Pg 也全過）

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/tools/lookups.py src/kinsun/db.py tests/test_web_search_store_contract.py
git commit -m "feat(tools): 新增上網查證來源紀錄持久層與 web_search_lookups 表"
```

---

### Task 2: web_search 工具（Tavily 呼叫＋分主題白名單）

**Files:**
- Create: `src/kinsun/tools/web_search.py`
- Test: `tests/test_tools_web_search.py`

**Interfaces:**
- Consumes（Task 1）：`WebSearchLookupStore`、`safe_record`、`STATUS_OK`／`STATUS_EMPTY`／`STATUS_ERROR`。
- Produces（Task 3）：
  - `WEB_SEARCH_SPEC: ToolSpec`（`name="web_search"`）
  - `build_web_search_handler(api_key: str, lookups: WebSearchLookupStore | None = None, transport: Transport | None = None) -> Callable[[dict], str]`
  - 主題常數 `TOPIC_GENERAL = "general"`、`TOPIC_HEALTH = "health"`、`TOPIC_RUMOR_CHECK = "rumor_check"`

- [ ] **Step 1: 寫失敗的測試** — `tests/test_tools_web_search.py`

```python
"""web_search 工具的離線測試：注入 FakeTransport 與 FakeWebSearchLookupStore，不連網。"""

from __future__ import annotations

import json

from kinsun.tools.lookups import STATUS_EMPTY, STATUS_ERROR, STATUS_OK, FakeWebSearchLookupStore
from kinsun.tools.web_search import WEB_SEARCH_SPEC, build_web_search_handler
from kinsun.transport import FakeTransport, Response, TransportError

_HIT = {
    "results": [
        {
            "title": "流感疫苗接種須知",
            "url": "https://www.cdc.gov.tw/flu",
            "content": "六十五歲以上長者可公費接種。",
            "score": 0.9,
        }
    ]
}


def _transport(payload):
    return FakeTransport([Response(200, {}, json.dumps(payload).encode())])


def _body(http: FakeTransport) -> dict:
    return json.loads(http.calls[0][2])


def _headers(http: FakeTransport) -> dict:
    return http.calls[0][3]


def test_spec_name_and_required_params():
    assert WEB_SEARCH_SPEC.name == "web_search"
    assert set(WEB_SEARCH_SPEC.parameters["required"]) == {"query", "topic"}


def test_calls_tavily_with_bearer_key():
    http = _transport(_HIT)
    build_web_search_handler("tvly-key", transport=http)({"query": "流感疫苗", "topic": "health"})
    method, url, _, headers, _ = http.calls[0]
    assert method == "POST"
    assert url == "https://api.tavily.com/search"
    assert headers["Authorization"] == "Bearer tvly-key"


def test_health_topic_sends_official_domain_whitelist():
    http = _transport(_HIT)
    build_web_search_handler("k", transport=http)({"query": "流感疫苗", "topic": "health"})
    assert _body(http)["include_domains"] == [
        "mohw.gov.tw",
        "cdc.gov.tw",
        "hpa.gov.tw",
        "fda.gov.tw",
        "nhi.gov.tw",
    ]


def test_rumor_check_topic_sends_fact_check_whitelist():
    http = _transport(_HIT)
    build_web_search_handler("k", transport=http)({"query": "喝這個治癌", "topic": "rumor_check"})
    assert _body(http)["include_domains"] == [
        "tfc-taiwan.org.tw",
        "mygopen.com",
        "165.npa.gov.tw",
    ]


def test_general_topic_sends_no_whitelist():
    http = _transport(_HIT)
    build_web_search_handler("k", transport=http)({"query": "今天油價", "topic": "general"})
    assert "include_domains" not in _body(http)


def test_result_carries_title_site_url_content():
    out = build_web_search_handler("k", transport=_transport(_HIT))(
        {"query": "流感疫苗", "topic": "health"}
    )
    payload = json.loads(out)
    assert payload["results"] == [
        {
            "title": "流感疫苗接種須知",
            "site": "cdc.gov.tw",
            "url": "https://www.cdc.gov.tw/flu",
            "content": "六十五歲以上長者可公費接種。",
        }
    ]


def test_records_sources_to_lookup_store():
    lookups = FakeWebSearchLookupStore()
    build_web_search_handler("k", lookups, _transport(_HIT))(
        {"query": "流感疫苗", "topic": "health"}
    )
    assert lookups.recorded == [
        (
            "流感疫苗",
            "health",
            STATUS_OK,
            [
                {
                    "title": "流感疫苗接種須知",
                    "site": "cdc.gov.tw",
                    "url": "https://www.cdc.gov.tw/flu",
                }
            ],
        )
    ]


def test_rumor_check_no_result_tells_agent_to_stay_conservative():
    lookups = FakeWebSearchLookupStore()
    out = build_web_search_handler("k", lookups, _transport({"results": []}))(
        {"query": "假訊息", "topic": "rumor_check"}
    )
    assert "查核網站" in out
    assert lookups.recorded[0][2] == STATUS_EMPTY


def test_transport_failure_returns_friendly_message_and_records_error():
    http = FakeTransport()
    http.error = TransportError("boom")
    lookups = FakeWebSearchLookupStore()
    out = build_web_search_handler("k", lookups, http)({"query": "油價", "topic": "general"})
    assert "暫時失敗" in out
    assert lookups.recorded[0][2] == STATUS_ERROR


def test_empty_query_asks_back():
    out = build_web_search_handler("k", transport=_transport(_HIT))(
        {"query": "  ", "topic": "general"}
    )
    assert "想查什麼" in out


def test_unknown_topic_is_rejected_without_searching():
    http = _transport(_HIT)
    out = build_web_search_handler("k", transport=http)({"query": "流感", "topic": "medical"})
    assert "topic" in out
    assert http.calls == []


def test_lookup_store_failure_does_not_break_reply():
    class _Boom:
        def record(self, **_kwargs):
            raise RuntimeError("db down")

    out = build_web_search_handler("k", _Boom(), _transport(_HIT))(
        {"query": "流感疫苗", "topic": "health"}
    )
    assert json.loads(out)["results"][0]["site"] == "cdc.gov.tw"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_tools_web_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kinsun.tools.web_search'`

- [ ] **Step 3: 寫最小實作** — `src/kinsun/tools/web_search.py`

```python
"""Tavily 上網查證工具：依主題套網域白名單，來源落 web_search_lookups 專表。

金孫的對象是長輩，錯誤資訊風險高，因此健康與謠言查證兩類**只採白名單來源**
（官方衛教網站／事實查核網站），一般時事才開放全網。HTTP 走共用傳輸層，
transport 可注入以利測試。
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Callable

from kinsun.llm import ToolSpec
from kinsun.tools.lookups import (
    STATUS_EMPTY,
    STATUS_ERROR,
    STATUS_OK,
    WebSearchLookupStore,
    safe_record,
)
from kinsun.transport import Transport, TransportError, UrllibTransport, read_json

logger = logging.getLogger("kinsun.tools.web_search")

TOPIC_GENERAL = "general"
TOPIC_HEALTH = "health"
TOPIC_RUMOR_CHECK = "rumor_check"

# 分主題網域白名單（spec 2026-07-14）：空 tuple＝不帶 include_domains（開放全網）。
_ALLOWED_DOMAINS: dict[str, tuple[str, ...]] = {
    TOPIC_GENERAL: (),
    TOPIC_HEALTH: ("mohw.gov.tw", "cdc.gov.tw", "hpa.gov.tw", "fda.gov.tw", "nhi.gov.tw"),
    TOPIC_RUMOR_CHECK: ("tfc-taiwan.org.tw", "mygopen.com", "165.npa.gov.tw"),
}

# 白名單內查無結果的回覆：查核類刻意不回退全網重搜，保守回覆即可（spec 決議）。
_EMPTY_REPLIES = {
    TOPIC_GENERAL: "網路上查不到相關資訊。",
    TOPIC_HEALTH: "官方衛教網站查不到相關資訊，請建議長輩問醫師或家人，不要自行補答案。",
    TOPIC_RUMOR_CHECK: (
        "查核網站沒有相關紀錄，無法確認真假。請保守回覆，"
        "建議長輩先問家人、不要轉傳，不要自行判定真假。"
    ),
}

_SEARCH_URL = "https://api.tavily.com/search"
_TIMEOUT_SECONDS = 10.0
_MAX_RESULTS = 5

WEB_SEARCH_SPEC = ToolSpec(
    name="web_search",
    description=(
        "上網查證即時或可疑資訊，回傳有來源網站的搜尋結果。"
        "長輩問時事、生活資訊（天氣以外）時用 topic=general；"
        "長輩轉述可疑訊息、疑似謠言或詐騙時用 topic=rumor_check（只查事實查核網站）；"
        "健康問題請**先**用 health_education_rag，"
        "只有在它回報查無資料且非高風險時，才用 topic=health 上官方衛教網站備援。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜尋關鍵字，例：今天油價、某某偏方"},
            "topic": {
                "type": "string",
                "enum": [TOPIC_GENERAL, TOPIC_HEALTH, TOPIC_RUMOR_CHECK],
                "description": "general＝一般時事；health＝官方衛教備援；rumor_check＝謠言查證",
            },
        },
        "required": ["query", "topic"],
    },
)


def _site_of(url: str) -> str:
    """從網址取出網域（去掉 www.），供金孫口語帶出來源。"""
    return urllib.parse.urlparse(url).netloc.removeprefix("www.")


def _search(http: Transport, api_key: str, query: str, topic: str) -> list[dict]:
    payload: dict = {
        "query": query,
        "search_depth": "basic",
        "max_results": _MAX_RESULTS,
    }
    domains = _ALLOWED_DOMAINS[topic]
    if domains:
        payload["include_domains"] = list(domains)
    response = http.request(
        "POST",
        _SEARCH_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=_TIMEOUT_SECONDS,
    )
    body = read_json(response)
    return [
        {
            "title": item.get("title", ""),
            "site": _site_of(item.get("url", "")),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        }
        for item in (body.get("results") or [])
    ]


def build_web_search_handler(
    api_key: str,
    lookups: WebSearchLookupStore | None = None,
    transport: Transport | None = None,
) -> Callable[[dict], str]:
    http = transport or UrllibTransport()

    def handler(args: dict) -> str:
        query = (args.get("query") or "").strip()
        topic = (args.get("topic") or "").strip()
        if not query:
            return "請告訴我您想查什麼。"
        if topic not in _ALLOWED_DOMAINS:
            # 未知主題不放行：健康問題誤搜全網的風險，比要模型重試一次高得多。
            return "（工具參數錯誤：topic 請用 general、health 或 rumor_check）"
        try:
            results = _search(http, api_key, query, topic)
        except TransportError:
            logger.warning("上網查證失敗：topic=%s query=%s", topic, query, exc_info=True)
            safe_record(lookups, query=query, topic=topic, status=STATUS_ERROR, sources=[])
            return "（上網查詢暫時失敗，請稍後再試）"
        if not results:
            safe_record(lookups, query=query, topic=topic, status=STATUS_EMPTY, sources=[])
            return _EMPTY_REPLIES[topic]
        safe_record(
            lookups,
            query=query,
            topic=topic,
            status=STATUS_OK,
            sources=[{k: r[k] for k in ("title", "site", "url")} for r in results],
        )
        return json.dumps({"topic": topic, "results": results}, ensure_ascii=False)

    return handler
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_tools_web_search.py -v`
Expected: PASS（13 passed）

- [ ] **Step 5: Commit**

```bash
git add src/kinsun/tools/web_search.py tests/test_tools_web_search.py
git commit -m "feat(tools): 新增 web_search 工具，依主題套網域白名單上網查證"
```

---

### Task 3: 接線（設定、組裝、系統提示、文件）

**Files:**
- Modify: `src/kinsun/config.py`、`src/kinsun/composition.py`、`src/kinsun/agent.py`、`.env.example`
- Test: `tests/test_composition.py`、`tests/test_config.py`

**Interfaces:**
- Consumes（Task 1、2）：`WEB_SEARCH_SPEC`、`build_web_search_handler`、`PgWebSearchLookupStore`。
- Produces：`build_tool_registry(*, clock, rag_service, tavily_api_key: str = "", lookups: WebSearchLookupStore | None = None) -> ToolRegistry`；`Settings.tavily_api_key: str`。

- [ ] **Step 1: 寫失敗的測試** — 在 `tests/test_config.py` 末尾新增：

```python
def test_tavily_api_key_defaults_to_empty():
    assert load_settings(_ENV).tavily_api_key == ""


def test_tavily_api_key_read_from_env():
    settings = load_settings({**_ENV, "TAVILY_API_KEY": "tvly-abc"})
    assert settings.tavily_api_key == "tvly-abc"
```

（`_ENV` 為該檔既有的最小環境變數 fixture 常數；若名稱不同，沿用該檔既有寫法。）

在 `tests/test_composition.py`：把既有的 `test_assemble_core_agent_has_all_three_tools`
與 `test_build_tool_registry_registers_three_tools` 保留（無金鑰＝仍是三個工具，
正是優雅降級的守門），並新增：

```python
def test_build_tool_registry_registers_web_search_when_key_present():
    registry = build_tool_registry(
        clock=_clock, rag_service=object(), tavily_api_key="tvly-key"
    )
    assert WEB_SEARCH_SPEC.name in {spec.name for spec in registry.specs()}


def test_build_tool_registry_skips_web_search_without_key():
    registry = build_tool_registry(clock=_clock, rag_service=object(), tavily_api_key="")
    assert WEB_SEARCH_SPEC.name not in {spec.name for spec in registry.specs()}
```

檔頭 import 補：`from kinsun.tools.web_search import WEB_SEARCH_SPEC`。

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_config.py tests/test_composition.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'tavily_api_key'` 與
`TypeError: build_tool_registry() got an unexpected keyword argument 'tavily_api_key'`

- [ ] **Step 3: 改 `src/kinsun/config.py`**

`Settings` 在 `rag_top_k: int` 之後新增欄位：

```python
    tavily_api_key: str
```

`load_settings` 在 `rag_top_k=...` 之後新增：

```python
        # 上網查證搜尋金鑰（spec 2026-07-14）：留空＝不註冊 web_search 工具（優雅降級）。
        tavily_api_key=env.get("TAVILY_API_KEY", ""),
```

- [ ] **Step 4: 改 `src/kinsun/composition.py`**

檔頭 import 補：

```python
from kinsun.tools.lookups import PgWebSearchLookupStore, WebSearchLookupStore
from kinsun.tools.web_search import WEB_SEARCH_SPEC, build_web_search_handler
```

`build_tool_registry` 改為：

```python
def build_tool_registry(
    *,
    clock: Callable[[], datetime],
    rag_service: HealthEducationRagService,
    tavily_api_key: str = "",
    lookups: WebSearchLookupStore | None = None,
) -> ToolRegistry:
    """集中組工具：日後新增工具只改這裡，兩個組裝根自動都有。"""
    registry = ToolRegistry()
    registry.register(WEATHER_SPEC, build_weather_handler())
    registry.register(CURRENT_TIME_SPEC, build_current_time_handler(clock))
    registry.register(HEALTH_RAG_SPEC, build_health_rag_handler(rag_service))
    # 金鑰未設＝跳過註冊（優雅降級）：金孫少一個上網查證能力，其餘功能照常運作。
    if tavily_api_key:
        registry.register(WEB_SEARCH_SPEC, build_web_search_handler(tavily_api_key, lookups))
    return registry
```

`assemble_core` 內，`agent = CareAgent(...)` 之前新增 store，並把兩個新參數傳進去：

```python
    web_search_lookups = PgWebSearchLookupStore(db, clock=clock, new_id=new_id)
    agent = CareAgent(
        externals.gemini,
        session,
        tools=build_tool_registry(
            clock=clock,
            rag_service=rag_service,
            tavily_api_key=settings.tavily_api_key,
            lookups=web_search_lookups,
        ),
    )
```

- [ ] **Step 5: 改 `src/kinsun/agent.py` 的 SYSTEM_PROMPT**

把既有這一句：

```python
    "查天氣前若不知道長輩人在哪個城市，先親口問清楚，不要自己猜地點。"
```

改成（在其後補上上網查證規則）：

```python
    "查天氣前若不知道長輩人在哪個城市，先親口問清楚，不要自己猜地點。"
    "長輩問時事或生活資訊、或轉述可疑訊息（疑似謠言、詐騙）時，用 web_search 工具查證；"
    "衛教問題一律先用 health_education_rag，它查不到才用 web_search。"
    "引用查到的內容要口語帶一句來源，例如「衛福部網站說」「查核中心說這是假的」，"
    "絕不唸出網址；查不到就保守回覆、建議長輩問家人或醫師，不可自行編答案。"
```

- [ ] **Step 6: 改 `.env.example`**

在 `GEMINI_TIMEOUT_SECONDS=30` 那一區塊之後新增：

```bash
# 上網查證（Tavily）金鑰；留空＝停用 web_search 工具，其餘功能照常。免費額度每月 1000 次。
TAVILY_API_KEY=
```

- [ ] **Step 7: 跑全套測試確認通過**

Run: `uv run pytest -q`
Expected: 全綠（既有測試無回歸）

- [ ] **Step 8: Commit**

```bash
git add src/kinsun/config.py src/kinsun/composition.py src/kinsun/agent.py .env.example tests/test_composition.py tests/test_config.py
git commit -m "feat(tools): 把 web_search 接進組裝與系統提示，金鑰未設則優雅降級"
```

---

## Self-Review

- **Spec 覆蓋**：工具介面（Task 2）、分主題白名單（Task 2）、Tavily 呼叫（Task 2）、資料庫專表與三件套（Task 1）、組裝與設定（Task 3）、系統提示（Task 3）、錯誤處理（Task 2 三種情境皆有測試）、測試（Task 1／2 各自的測試檔＋Task 3 守門）、文件同步（Task 3 `.env.example`）。無遺漏。
- **型別一致**：`safe_record` 在 `lookups.py` 定義、`web_search.py` 使用，簽名一致（全 keyword-only）。`FakeWebSearchLookupStore.recorded` 的 tuple 順序 `(query, topic, status, sources)` 在 Task 2 測試中與 Task 1 實作一致。
- **已知限制（spec 已載明）**：工具 handler 拿不到 `elder_id`／`trace_id`，本表不含長輩關聯；日後如需，另案擴充 `ToolRegistry.dispatch` 介面。
