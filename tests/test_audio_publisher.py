import json
from datetime import datetime, timedelta, timezone

import pytest

from kinsun.audio.publisher import (
    AudioPublishError,
    SupabaseAudioPublisher,
    build_audio_publisher,
)
from kinsun.transport import FakeTransport, Response, TransportError

_TPE = timezone(timedelta(hours=8))
_NOW = datetime(2026, 7, 2, 9, 0, tzinfo=_TPE)


def _publisher(transport, **kwargs):
    return SupabaseAudioPublisher(
        "https://proj.supabase.co",
        "service-key",
        "tts-audio",
        timeout=10.0,
        clock=lambda: _NOW,
        new_id=lambda: "abc123",
        transport=transport,
        **kwargs,
    )


def test_publish_uploads_and_returns_public_url():
    transport = FakeTransport([Response(200, {}, b"{}")])
    url = _publisher(transport).publish(b"AUDIO", content_type="audio/mp4")
    assert url == (
        "https://proj.supabase.co/storage/v1/object/public/tts-audio/tts/20260702/abc123.m4a"
    )
    method, call_url, data, headers, _timeout = transport.calls[0]
    assert method == "POST"
    assert call_url == (
        "https://proj.supabase.co/storage/v1/object/tts-audio/tts/20260702/abc123.m4a"
    )
    assert headers["Authorization"] == "Bearer service-key"
    assert headers["Content-Type"] == "audio/mp4"
    assert data == b"AUDIO"


def test_publish_transport_error_raises():
    transport = FakeTransport()
    transport.error = TransportError("boom")
    with pytest.raises(AudioPublishError):
        _publisher(transport).publish(b"A", content_type="audio/mp4")


def test_cleanup_deletes_expired_date_folders():
    def handler(method, url, data):
        if method == "POST":
            prefix = json.loads(data)["prefix"]
            bodies = {
                "tts/": b'[{"name":"20260628"},{"name":"20260630"},{"name":"20260702"}]',
                "tts/20260628/": b'[{"name":"a.m4a"},{"name":"b.m4a"}]',
                "tts/20260630/": b'[{"name":"c.m4a"}]',
            }
            return Response(200, {}, bodies.get(prefix, b"[]"))
        return Response(200, {}, b"{}")  # DELETE

    transport = FakeTransport(handler=handler)
    _publisher(transport).cleanup(retention_days=2)  # 保留 20260701~ ；刪 0628、0630

    deletes = [
        (url, json.loads(data))
        for method, url, data, _headers, _timeout in transport.calls
        if method == "DELETE"
    ]
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


def test_object_path_uses_prefix():
    publisher = SupabaseAudioPublisher(
        "https://sb.example",
        "key",
        "bucket",
        timeout=1.0,
        clock=lambda: datetime(2026, 7, 3, 12, 0),
        new_id=lambda: "abc",
        prefix="inbound",
    )
    assert publisher._object_path("abc.m4a") == "inbound/20260703/abc.m4a"
