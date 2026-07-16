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
