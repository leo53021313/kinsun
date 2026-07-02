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
        calls.append((req.get_method(), req.full_url, req.data))

        class _R:
            def read(self):
                # list bucket 回三個日期資料夾
                return b'[{"name":"20260628"},{"name":"20260630"},{"name":"20260702"}]'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _R()

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
    deleted = [url for method, url, _ in calls if method == "DELETE"]
    assert any("20260628" in u for u in deleted)
    assert any("20260630" in u for u in deleted)
    assert not any("20260702" in u for u in deleted)


def test_build_requires_supabase_config():
    class _S:
        supabase_url = ""
        supabase_service_key = ""
        audio_bucket = "tts-audio"
        audio_upload_timeout_seconds = 10.0

    with pytest.raises(AudioPublishError):
        build_audio_publisher(_S(), clock=lambda: _NOW, new_id=lambda: "x")
