"""Tavily 上網查證工具：依主題套網域白名單，來源落 web_search_lookups 專表。

金孫的對象是長輩，錯誤資訊風險高，因此健康與謠言查證兩類**只採白名單來源**（官方
衛教網站／事實查核網站），一般時事才開放全網。HTTP 走共用傳輸層，transport 可注入
以利測試。
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

# 白名單內查無結果的回覆：查核類刻意不回退全網重搜（spec 決議），保守回覆即可。
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
        "上網查證即時或可疑資訊，回傳附來源網站的搜尋結果。"
        "長輩問時事、生活資訊（天氣除外）時用 topic=general；"
        "長輩轉述可疑訊息、疑似謠言或詐騙時用 topic=rumor_check，只查事實查核網站；"
        "健康問題一律先用 health_education_rag，"
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
    payload: dict = {"query": query, "search_depth": "basic", "max_results": _MAX_RESULTS}
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
            # 未知主題不放行：健康問題誤搜到內容農場的風險，遠高於要模型重試一次的成本。
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
            sources=[{key: r[key] for key in ("title", "site", "url")} for r in results],
        )
        return json.dumps({"topic": topic, "results": results}, ensure_ascii=False)

    return handler
