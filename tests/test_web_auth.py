import pytest

from kinsun.transport import FakeTransport, Response, TransportError
from kinsun.web.auth import AuthError, LineIdTokenVerifier


def test_verify_returns_sub():
    transport = FakeTransport([Response(200, {}, b'{"sub": "U-123"}')])
    assert LineIdTokenVerifier("ch", 10, transport=transport).verify("tok") == "U-123"
    method, url, data, headers, _timeout = transport.calls[0]
    assert (method, url) == ("POST", "https://api.line.me/oauth2/v2.1/verify")
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert b"id_token=tok" in data


def test_verify_missing_sub_raises():
    transport = FakeTransport([Response(200, {}, b'{"aud": "ch"}')])
    with pytest.raises(AuthError):
        LineIdTokenVerifier("ch", 10, transport=transport).verify("tok")


def test_verify_transport_error_raises():
    transport = FakeTransport()
    transport.error = TransportError("bad")
    with pytest.raises(AuthError):
        LineIdTokenVerifier("ch", 10, transport=transport).verify("tok")
