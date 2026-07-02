import json
from datetime import datetime, timedelta, timezone

import pytest

from kinsun.audio.publisher import (
    AudioPublishError,
    SupabaseAudioPublisher,
    build_audio_publisher,
)

_TPE = timezone(timedelta(hours=8))
_NOW = datetime(2026, 7, 2, 9, 0, tzinfo=_TPE)


def _publisher(monkeypatch, capture):
    def fake_urlopen(req, timeout=None):
        capture["url"] = req.full_url
        capture["method"] = req.get_method()
        capture["auth"] = req.headers.get("Authorization")
        capture["ctype"] = req.headers.get("Content-type")
        capture["body"] = req.data

        class _R:
            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _R()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return SupabaseAudioPublisher(
        "https://proj.supabase.co",
        "service-key",
        "tts-audio",
        timeout=10.0,
        clock=lambda: _NOW,
        new_id=lambda: "abc123",
    )


def test_publish_uploads_and_returns_public_url(monkeypatch):
    capture = {}
    url = _publisher(monkeypatch, capture).publish(b"AUDIO", content_type="audio/mp4")
    assert url == (
        "https://proj.supabase.co/storage/v1/object/public/tts-audio/tts/20260702/abc123.m4a"
    )
    assert capture["url"] == (
        "https://proj.supabase.co/storage/v1/object/tts-audio/tts/20260702/abc123.m4a"
    )
    assert capture["method"] == "POST"
    assert capture["auth"] == "Bearer service-key"
    assert capture["ctype"] == "audio/mp4"
    assert capture["body"] == b"AUDIO"


def test_publish_http_error_raises(monkeypatch):
    import urllib.error

    def boom(req, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    pub = SupabaseAudioPublisher(
        "https://proj.supabase.co", "k", "b", timeout=10.0, clock=lambda: _NOW, new_id=lambda: "x"
    )
    with pytest.raises(AudioPublishError):
        pub.publish(b"A", content_type="audio/mp4")


def test_cleanup_deletes_expired_date_folders(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None):
        method = req.get_method()
        url = req.full_url
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        calls.append((method, url, body))

        class _R:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        if method == "POST":
            # list 端點：依 prefix 回不同層級的內容
            prefix = body["prefix"]
            if prefix == "tts/":
                # 頂層：三個日期資料夾
                return _R(b'[{"name":"20260628"},{"name":"20260630"},{"name":"20260702"}]')
            if prefix == "tts/20260628/":
                return _R(b'[{"name":"a.m4a"},{"name":"b.m4a"}]')
            if prefix == "tts/20260630/":
                return _R(b'[{"name":"c.m4a"}]')
            return _R(b"[]")
        # DELETE：bulk 刪除
        return _R(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    pub = SupabaseAudioPublisher(
        "https://proj.supabase.co",
        "k",
        "tts-audio",
        timeout=10.0,
        clock=lambda: _NOW,
        new_id=lambda: "x",
    )
    pub.cleanup(retention_days=2)  # 保留 20260701~ ；刪 0628、0630

    deletes = [(url, body) for method, url, body in calls if method == "DELETE"]
    assert deletes, "應觸發至少一次 bulk DELETE"
    for url, _ in deletes:
        assert url == "https://proj.supabase.co/storage/v1/object/tts-audio"
    all_paths = [p for _, body in deletes for p in body["paths"]]
    assert "tts/20260628/a.m4a" in all_paths
    assert "tts/20260628/b.m4a" in all_paths
    assert "tts/20260630/c.m4a" in all_paths
    assert not any("20260702" in p for p in all_paths)


def test_build_requires_supabase_config():
    class _S:
        supabase_url = ""
        supabase_service_key = ""
        audio_bucket = "tts-audio"
        audio_upload_timeout_seconds = 10.0

    with pytest.raises(AudioPublishError):
        build_audio_publisher(_S(), clock=lambda: _NOW, new_id=lambda: "x")
