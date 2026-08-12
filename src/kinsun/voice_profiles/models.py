"""聲音設定檔的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceProfile:
    elder_id: str
    # 參考音檔在 Supabase bucket 內的**物件路徑**（如 voice-refs/<elder_id>.wav）。
    # ⚠️ 刻意不存簽章 URL：那種 URL 會過期（預設 1 天），過期後 DGX 端下載失敗會讓整輪
    # 退化成純文字、長輩完全沒聲音。改由應用層在每次組 VoiceReference 時現簽短效 URL。
    prompt_audio_path: str
    prompt_text: str  # 參考音檔逐字稿
    consented_by: str  # 誰同意複製這段聲音（自由文字，如「孫子小明本人於通話中同意」）
    granted_at: float
    revoked_at: float | None = None
