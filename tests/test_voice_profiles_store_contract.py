"""VoiceProfileStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員」關係斷言而互不干擾。
"""

from __future__ import annotations

import pytest

from kinsun.voice_profiles.models import VoiceProfile
from kinsun.voice_profiles.store import FakeVoiceProfileStore, PgVoiceProfileStore


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgVoiceProfileStore(request.getfixturevalue("pg_database"))
    return FakeVoiceProfileStore()


def test_save_and_get_active_roundtrip(store, ns):
    profile = VoiceProfile(
        elder_id=f"{ns}e1",
        prompt_audio_path="voice-refs/voice.wav",
        prompt_text="午安，我是小明。",
        consented_by="孫子小明本人於通話中同意",
        granted_at=1000.0,
    )
    store.save(profile)
    got = store.get_active(f"{ns}e1")
    assert got == profile


def test_get_active_returns_none_when_missing(store, ns):
    assert store.get_active(f"{ns}nope") is None


def test_save_upserts_existing_profile(store, ns):
    store.save(
        VoiceProfile(
            elder_id=f"{ns}e1",
            prompt_audio_path="voice-refs/v1.wav",
            prompt_text="舊逐字稿",
            consented_by="舊同意人",
            granted_at=1000.0,
        )
    )
    store.save(
        VoiceProfile(
            elder_id=f"{ns}e1",
            prompt_audio_path="voice-refs/v2.wav",
            prompt_text="新逐字稿",
            consented_by="新同意人",
            granted_at=2000.0,
        )
    )
    got = store.get_active(f"{ns}e1")
    assert got.prompt_audio_path == "voice-refs/v2.wav"
    assert got.prompt_text == "新逐字稿"


def test_revoke_makes_profile_inactive(store, ns):
    store.save(
        VoiceProfile(
            elder_id=f"{ns}e1",
            prompt_audio_path="voice-refs/voice.wav",
            prompt_text="逐字稿",
            consented_by="同意人",
            granted_at=1000.0,
        )
    )
    store.revoke(f"{ns}e1", revoked_at=1500.0)
    assert store.get_active(f"{ns}e1") is None
