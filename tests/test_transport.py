"""傳輸層單元測試：get_json／read_json 用 FakeTransport（離線），
HttpxTransport 的 httpx 整合則以 httpx.MockTransport 注入假回應（測 adapter 本身）。
"""

from __future__ import annotations

import httpx
import pytest

from kinsun.transport import (
    FakeTransport,
    HttpxTransport,
    Response,
    TransportError,
    get_json,
    header_value,
    read_json,
)


def test_header_value_matches_case_insensitively():
    """HTTP 標頭名不分大小寫：真實線路上 uvicorn/Starlette 一律送小寫
    （如 x-duration-ms），讀取端不可假設寫法。"""
    response = Response(200, {"x-duration-ms": "680"}, b"")
    assert header_value(response, "X-Duration-Ms") == "680"
    assert header_value(response, "x-duration-ms") == "680"


def test_header_value_returns_none_when_absent():
    assert header_value(Response(200, {}, b""), "X-Duration-Ms") is None


def test_get_json_issues_get_and_decodes_body():
    transport = FakeTransport([Response(200, {}, b'{"text": "\\u4f60\\u597d"}')])
    assert get_json(transport, "http://x/y", timeout=5) == {"text": "你好"}
    method, url, _data, _headers, timeout = transport.calls[0]
    assert (method, url, timeout) == ("GET", "http://x/y", 5)


def test_read_json_bad_body_raises_transport_error():
    with pytest.raises(TransportError):
        read_json(Response(200, {}, b"not json"))


def test_get_json_propagates_transport_error_from_transport():
    transport = FakeTransport()
    transport.error = TransportError("boom")
    with pytest.raises(TransportError):
        get_json(transport, "http://x", timeout=5)


def test_fake_transport_handler_dispatches_on_request():
    def handler(method, url, data):
        return Response(200, {}, method.encode())

    transport = FakeTransport(handler=handler)
    assert transport.request("DELETE", "http://x", timeout=5).body == b"DELETE"
    assert transport.request("GET", "http://x", timeout=5).body == b"GET"


def _mock_client(handler) -> httpx.Client:
    """建一個以 httpx.MockTransport 攔截請求的 client，供 adapter 測試注入。"""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_httpx_transport_returns_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["content"] = request.content
        return httpx.Response(200, headers={"X-Duration-Ms": "42"}, content=b"audio-bytes")

    resp = HttpxTransport(client=_mock_client(handler)).request(
        "POST", "http://dgx/x", data=b"payload", timeout=8
    )
    assert resp.status == 200
    # httpx 將標頭名正規化為小寫（與真實線路一致）；讀取端一律走大小寫不敏感的 header_value。
    assert header_value(resp, "X-Duration-Ms") == "42"
    assert resp.body == b"audio-bytes"
    assert captured == {"method": "POST", "content": b"payload"}


def test_httpx_transport_wraps_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(TransportError):
        HttpxTransport(client=_mock_client(handler)).request("GET", "http://dgx/x", timeout=8)


def test_httpx_transport_wraps_non_2xx_status():
    """非 2xx 一律翻成 TransportError（對齊原 urllib 版對 4xx/5xx 拋 HTTPError 的行為）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found")

    with pytest.raises(TransportError):
        HttpxTransport(client=_mock_client(handler)).request("GET", "http://dgx/x", timeout=8)
