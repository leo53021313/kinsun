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


_SIGN_RESPONSE = Response(
    200,
    {},
    b'{"signedURL":"/object/sign/tts-audio/tts/20260702/abc123.m4a?token=tok"}',
)


def _publisher(transport, **kwargs):
    return SupabaseAudioPublisher(
        "https://proj.supabase.co",
        "service-key",
        "tts-audio",
        timeout=10.0,
        clock=lambda: _NOW,
        new_id=lambda: "abc123",
        transport=transport,
        signed_url_expires_seconds=600,
        **kwargs,
    )


def test_publish_uploads_and_returns_signed_url():
    transport = FakeTransport([Response(200, {}, b"{}"), _SIGN_RESPONSE])
    url = _publisher(transport).publish(b"AUDIO", content_type="audio/mp4")
    assert url == (
        "https://proj.supabase.co/storage/v1"
        "/object/sign/tts-audio/tts/20260702/abc123.m4a?token=tok"
    )
    method, call_url, data, headers, _timeout = transport.calls[0]
    assert method == "POST"
    assert call_url == (
        "https://proj.supabase.co/storage/v1/object/tts-audio/tts/20260702/abc123.m4a"
    )
    assert headers["Authorization"] == "Bearer service-key"
    assert headers["Content-Type"] == "audio/mp4"
    assert data == b"AUDIO"


def test_publish_requests_signed_url_with_expiry():
    transport = FakeTransport([Response(200, {}, b"{}"), _SIGN_RESPONSE])
    _publisher(transport).publish(b"AUDIO", content_type="audio/mp4")
    method, call_url, data, headers, _timeout = transport.calls[1]
    assert method == "POST"
    assert call_url == (
        "https://proj.supabase.co/storage/v1/object/sign/tts-audio/tts/20260702/abc123.m4a"
    )
    assert json.loads(data) == {"expiresIn": 600}
    assert headers["Authorization"] == "Bearer service-key"
    assert headers["Content-Type"] == "application/json"


def test_publish_sign_response_missing_url_raises():
    transport = FakeTransport([Response(200, {}, b"{}"), Response(200, {}, b"{}")])
    with pytest.raises(AudioPublishError):
        _publisher(transport).publish(b"AUDIO", content_type="audio/mp4")


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
    # Supabase 批次刪除的 body 鍵是 `prefixes`（2026-08-19 對真 Supabase 實測：
    # `paths` 一律 400，撤銷刪檔上線以來從未成功過）。
    all_paths = [p for _, body in deletes for p in body["prefixes"]]
    assert "tts/20260628/a.m4a" in all_paths
    assert "tts/20260628/b.m4a" in all_paths
    assert "tts/20260630/c.m4a" in all_paths
    assert not any("20260702" in p for p in all_paths)


def test_cleanup_disabled_when_retention_nonpositive():
    """retention_days<=0＝不清理（2026-07-09 修訂：音檔本體先不刪）——不得發出任何請求。"""
    transport = FakeTransport()
    _publisher(transport).cleanup(retention_days=0)
    assert transport.calls == []


def test_build_requires_supabase_config():
    class _S:
        supabase_url = ""
        supabase_service_key = ""
        audio_bucket = "tts-audio"
        audio_upload_timeout_seconds = 10.0
        audio_signed_url_expires_seconds = 86400

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


# --- 長輩客製化聲音參考音檔的簽章（2026-08-01） ---

_VOICE_SIGN_RESPONSE = Response(
    200,
    {},
    b'{"signedURL":"/object/sign/tts-audio/voice-refs/e1.wav?token=vtok"}',
)


def test_signed_url_for_signs_an_existing_object_without_uploading():
    """voice_profiles 存的是物件路徑，這裡只簽網址、不上傳。"""
    transport = FakeTransport([_VOICE_SIGN_RESPONSE])
    url = _publisher(transport).signed_url_for("voice-refs/e1.wav")

    assert url == (
        "https://proj.supabase.co/storage/v1/object/sign/tts-audio/voice-refs/e1.wav?token=vtok"
    )
    assert len(transport.calls) == 1, "只該打簽章端點，不該有上傳"
    method, call_url, data, _headers, _timeout = transport.calls[0]
    assert method == "POST"
    assert call_url == "https://proj.supabase.co/storage/v1/object/sign/tts-audio/voice-refs/e1.wav"
    assert json.loads(data)["expiresIn"] == 3600, "用參考音檔專屬效期，不是回覆音檔那個"


def test_signed_url_for_reuses_the_cached_url_within_its_lifetime():
    """效期內重用：實測簽一次約 384ms，且落在長輩等回覆的關鍵路徑上。

    DGX 端拿到音檔後會自行快取、之後根本用不到這個網址，但應用層無從得知對方的
    快取狀態，只能每輪都附上——所以省下這次往返的唯一辦法就是自己記住。
    """
    transport = FakeTransport([_VOICE_SIGN_RESPONSE])
    publisher = _publisher(transport)

    first = publisher.signed_url_for("voice-refs/e1.wav")
    second = publisher.signed_url_for("voice-refs/e1.wav")

    assert first == second
    assert len(transport.calls) == 1, "第二次不該再打 Supabase"


def test_signed_url_for_resigns_after_the_cache_entry_expires():
    """換發要早於網址本身到期，免得把「剩沒幾秒」的網址交給 DGX 而在下載途中過期。"""
    now = _NOW
    transport = FakeTransport([_VOICE_SIGN_RESPONSE, _VOICE_SIGN_RESPONSE])
    publisher = SupabaseAudioPublisher(
        "https://proj.supabase.co",
        "service-key",
        "tts-audio",
        timeout=10.0,
        clock=lambda: now,
        new_id=lambda: "abc123",
        transport=transport,
    )

    publisher.signed_url_for("voice-refs/e1.wav")
    now = _NOW + timedelta(seconds=3600 - 300 + 1)  # 過了換發點（效期 3600、提前 300 換）
    publisher.signed_url_for("voice-refs/e1.wav")

    assert len(transport.calls) == 2


def test_signed_url_for_caches_per_path():
    """兩位長輩各有各的參考音檔，不能互相汙染。"""
    transport = FakeTransport([_VOICE_SIGN_RESPONSE, _VOICE_SIGN_RESPONSE])
    publisher = _publisher(transport)

    publisher.signed_url_for("voice-refs/e1.wav")
    publisher.signed_url_for("voice-refs/e2.wav")

    assert len(transport.calls) == 2
    assert transport.calls[1][1].endswith("/voice-refs/e2.wav")


def test_signed_url_for_resigns_when_the_voice_version_changes():
    """家屬重錄＝版本換值＝立刻重簽，不等快取到期（2026-08-19）。

    正式環境跑多個 uvicorn worker：`upload_voice_reference` 只清得掉收到 PUT 的那個
    worker 的快取，其他 worker 手上重錄**之前**簽的網址還有最長 55 分鐘壽命。物件
    路徑固定不變，CDN 又是按完整 URL 快取——舊網址可能命中重錄前的舊音檔，DGX 端
    再把它記在**新版本**底下，舊聲音從此黏死。版本一換就重簽＝新 token＝全新 URL，
    兩層舊快取一次繞過。
    """
    transport = FakeTransport([_VOICE_SIGN_RESPONSE, _VOICE_SIGN_RESPONSE])
    publisher = _publisher(transport)

    publisher.signed_url_for("voice-refs/e1.wav", "1000.0")
    publisher.signed_url_for("voice-refs/e1.wav", "1000.0")  # 同版本：照常吃快取
    assert len(transport.calls) == 1

    publisher.signed_url_for("voice-refs/e1.wav", "2000.0")  # 重錄後第一次：必須重簽
    assert len(transport.calls) == 2, "版本換了卻沒重簽＝其他 worker 會把舊網址發到效期結束"


def test_delete_voice_reference_removes_the_object_and_drops_the_cached_url():
    """撤銷客製化聲音要真的把聲音樣本刪掉（2026-08-12）。

    這是長輩家人的聲紋，不是一般的回覆音檔——`cleanup(retention_days)` 只掃 `tts/`
    底下的日期資料夾，`voice-refs/` 不在它的範圍內，沒有這支就等於「家屬按了撤銷、
    檔案永遠留著」。
    """
    transport = FakeTransport([Response(200, {}, b"{}")])
    publisher = _publisher(transport)
    publisher._voice_url_cache["voice-refs/e1"] = (
        "https://stale.test/x",
        _NOW + timedelta(1),
        "1000.0",
    )

    publisher.delete_voice_reference("e1")

    method, url, data, _headers, _timeout = transport.calls[0]
    assert method == "DELETE"
    assert url == "https://proj.supabase.co/storage/v1/object/tts-audio"
    assert json.loads(data) == {"prefixes": ["voice-refs/e1"]}, (
        "鍵名必須是 prefixes——用 paths 真 Supabase 回 400、聲紋永遠刪不掉（2026-08-19 實測）"
    )
    # 簽章快取一併清掉，否則撤銷後那個網址在效期內仍然簽得出來、指向剛被刪的物件。
    assert publisher._voice_url_cache == {}


def test_delete_voice_reference_failing_does_not_raise():
    """刪不掉只記警告：撤銷的權威是資料庫那筆 `revoked_at`，不是這次網路呼叫。

    反過來設計（刪檔失敗就讓撤銷失敗）會讓家屬按了撤銷卻收到錯誤，而聲音其實
    已經停用了——那比留一個孤兒檔案更糟。
    """
    transport = FakeTransport([TransportError("boom")])
    publisher = _publisher(transport)
    publisher.delete_voice_reference("e1")  # 不可拋
