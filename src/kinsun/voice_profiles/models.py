"""聲音設定檔的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceProfile:
    elder_id: str
    prompt_audio_url: str  # 參考音檔（Supabase 簽章 URL）
    prompt_text: str  # 參考音檔逐字稿
    consented_by: str  # 誰同意複製這段聲音（自由文字，如「孫子小明本人於通話中同意」）
    granted_at: float
    revoked_at: float | None = None
