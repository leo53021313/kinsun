import json
import urllib.error

import pytest

from kinsun.web.auth import AuthError, LineIdTokenVerifier


class _FakeResp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_verify_returns_sub(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _FakeResp({"sub": "U-123"})
    )
    assert LineIdTokenVerifier("ch", 10).verify("tok") == "U-123"


def test_verify_missing_sub_raises(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _FakeResp({"aud": "ch"})
    )
    with pytest.raises(AuthError):
        LineIdTokenVerifier("ch", 10).verify("tok")


def test_verify_http_error_raises(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("bad")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(AuthError):
        LineIdTokenVerifier("ch", 10).verify("tok")
