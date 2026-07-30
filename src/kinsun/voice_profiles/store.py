"""聲音設定檔的儲存層：Protocol、Postgres 實作與測試替身。"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.voice_profiles.models import VoiceProfile


class VoiceProfileError(Exception):
    """聲音設定檔讀寫失敗。"""


class VoiceProfileStore(Protocol):
    def save(self, profile: VoiceProfile) -> None: ...
    def get_active(self, elder_id: str) -> VoiceProfile | None: ...
    def revoke(self, elder_id: str, *, revoked_at: float) -> None: ...


class PgVoiceProfileStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: VoiceProfileError(f"聲音設定檔存取失敗：{m}"))

    def save(self, profile: VoiceProfile) -> None:
        self._db.execute(
            "INSERT INTO voice_profiles "
            "(elder_id, prompt_audio_url, prompt_text, consented_by, granted_at, revoked_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (elder_id) DO UPDATE SET "
            "prompt_audio_url = EXCLUDED.prompt_audio_url, prompt_text = EXCLUDED.prompt_text, "
            "consented_by = EXCLUDED.consented_by, granted_at = EXCLUDED.granted_at, "
            "revoked_at = EXCLUDED.revoked_at",
            (
                profile.elder_id,
                profile.prompt_audio_url,
                profile.prompt_text,
                profile.consented_by,
                profile.granted_at,
                profile.revoked_at,
            ),
        )

    def get_active(self, elder_id: str) -> VoiceProfile | None:
        rows = self._db.query(
            "SELECT elder_id, prompt_audio_url, prompt_text, consented_by, granted_at, revoked_at "
            "FROM voice_profiles WHERE elder_id = %s AND revoked_at IS NULL",
            (elder_id,),
        )
        return VoiceProfile(*rows[0]) if rows else None

    def revoke(self, elder_id: str, *, revoked_at: float) -> None:
        self._db.execute(
            "UPDATE voice_profiles SET revoked_at = %s WHERE elder_id = %s",
            (revoked_at, elder_id),
        )


class FakeVoiceProfileStore:
    """VoiceProfileStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._profiles: dict[str, VoiceProfile] = {}

    def save(self, profile: VoiceProfile) -> None:
        self._profiles[profile.elder_id] = profile

    def get_active(self, elder_id: str) -> VoiceProfile | None:
        profile = self._profiles.get(elder_id)
        if profile is None or profile.revoked_at is not None:
            return None
        return profile

    def revoke(self, elder_id: str, *, revoked_at: float) -> None:
        profile = self._profiles.get(elder_id)
        if profile is not None:
            self._profiles[elder_id] = replace(profile, revoked_at=revoked_at)
