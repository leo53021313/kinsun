"""傳輸層單元測試：get_json／read_json 用 FakeTransport（離線），
UrllibTransport 的 urllib 整合則就地 monkeypatch urlopen（測 adapter 本身）。
"""

from __future__ import annotations

import urllib.error

import pytest

from kinsun.transport import (
    FakeTransport,
    Response,
    TransportError,
    UrllibTransport,
    get_json,
    read_json,
)


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


class _FakeHttpResponse:
    def __init__(self, status: int, headers: dict, body: bytes) -> None:
        self.status = status
        self.headers = _FakeHeaders(headers)
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeHeaders:
    def __init__(self, headers: dict) -> None:
        self._headers = headers

    def items(self):
        return self._headers.items()


def test_urllib_transport_returns_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        return _FakeHttpResponse(200, {"X-Duration-Ms": "42"}, b"audio-bytes")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    resp = UrllibTransport().request("POST", "http://dgx/x", data=b"payload", timeout=8)
    assert resp.status == 200
    assert resp.headers["X-Duration-Ms"] == "42"
    assert resp.body == b"audio-bytes"
    assert captured == {"method": "POST", "timeout": 8}


def test_urllib_transport_wraps_urlerror(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(TransportError):
        UrllibTransport().request("GET", "http://dgx/x", timeout=8)
