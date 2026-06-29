import pytest

from kinsun.config import load_settings
from kinsun.speech.asr import ASRClient, ASRError, MockAsrClient, build_asr_client

BASE_ENV = {
    "LINE_CHANNEL_SECRET": "s",
    "LINE_CHANNEL_ACCESS_TOKEN": "t",
    "GEMINI_API_KEY": "k",
    "DATABASE_URL": "postgresql://u:p@h:5432/db",
}


def test_mock_returns_configured_transcript():
    client = MockAsrClient("阿公早安")
    assert client.transcribe(b"\x00\x01", content_type="audio/m4a") == "阿公早安"


def test_build_returns_mock_for_mock_backend():
    settings = load_settings(BASE_ENV)
    client = build_asr_client(settings)
    assert isinstance(client, MockAsrClient)


def test_build_dgx_without_endpoint_raises():
    settings = load_settings({**BASE_ENV, "ASR_BACKEND": "dgx"})
    with pytest.raises(ASRError):
        build_asr_client(settings)


def test_mock_satisfies_protocol():
    client: ASRClient = MockAsrClient()
    assert client.transcribe(b"x", content_type="audio/m4a")
