"""長輩客製化聲音設定檔：家屬錄一段照唸的參考語音，長輩往後就聽到那個聲音。

與 `voice_profiles/store.py` 的分工：本檔是 HTTP 邊界（權限、驗證、音檔上傳），
持久層與領域模型在該套件裡。

⚠️ 為什麼「錄音內容」是系統給的固定稿（`voice_profiles/script.py`）而不是自由發揮：
CosyVoice zero-shot 要「參考音檔 ＋ 那段音檔的逐字稿」成對輸入，逐字稿一旦對不上
音檔，合成品質就壞掉且無聲無息。固定稿讓逐字稿**不是猜出來的**，同時把
`services/tts/README.md` 那四條錄製準則從「靠人自律」變成內建。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from kinsun.audio.publisher import AudioPublishError
from kinsun.voice_profiles.models import VoiceProfile
from kinsun.voice_profiles.script import (
    SCRIPT_RATIONALE,
    VOICE_PROFILE_SCRIPT,
    VOICE_PROFILE_TIPS,
)
from kinsun.voice_profiles.store import VoiceProfileError, VoiceProfileStore
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode
from kinsun.web.routers.deps import GuardianAuth, GuardianScope

# 參考音檔上限（bytes）。15 秒的錄音遠低於此；上限存在是為了擋住誤傳的大檔，
# 不是為了限制正常使用。與對講機單回合上限（10MB）同級。
_MAX_REFERENCE_BYTES = 10 * 1024 * 1024


def create_voice_profiles_router(
    *,
    voice_profiles: VoiceProfileStore | None,
    publisher,
    current_guardian: Callable[..., GuardianAuth],
    scope: GuardianScope,
    clock: Callable[[], datetime],
) -> APIRouter:
    """`voice_profiles`／`publisher` 任一為 None＝功能未啟用（TTS 非 dgx 或缺 Supabase）。

    未啟用時端點仍存在但一律回 503，而不是整支 router 消失——404 會讓前端誤以為
    自己打錯路徑，503 才講得出「這個環境沒開這個功能」。
    """
    router = APIRouter(tags=["voice-profiles"])

    def _require_enabled() -> None:
        if voice_profiles is None or publisher is None:
            raise HTTPException(status_code=503, detail=ErrorCode.SPEECH_UNAVAILABLE)

    @router.get("/voice-profile-script")
    def get_script() -> dict:
        """家屬錄音前要照唸的稿子與注意事項。

        由伺服器下發而非寫死在前端：稿子改動時（例如發現某個字念不準要加進去）
        只需改一處，不必等前端跟著發版；而逐字稿與稿子必須是同一份文字，
        分兩邊維護遲早會漂移。
        """
        return ok(
            {
                "script": VOICE_PROFILE_SCRIPT,
                "tips": list(VOICE_PROFILE_TIPS),
                "rationale": SCRIPT_RATIONALE,
            }
        )

    @router.get("/elders/{elder_id}/voice-profile")
    def get_voice_profile(elder_id: str, auth: GuardianAuth = Depends(current_guardian)) -> dict:
        """查這位長輩目前有沒有生效中的客製化聲音。

        ⚠️ 不回傳音檔也不回傳可下載的網址：那是長輩家人的聲音樣本，
        查詢設定狀態不需要能把它拿走。
        """
        scope.assert_manages(auth, elder_id)
        _require_enabled()
        profile = voice_profiles.get_active(elder_id)
        if profile is None:
            return ok({"elder_id": elder_id, "has_profile": False})
        return ok(
            {
                "elder_id": elder_id,
                "has_profile": True,
                "consented_by": profile.consented_by,
                "granted_at": profile.granted_at,
            }
        )

    @router.put("/elders/{elder_id}/voice-profile")
    async def set_voice_profile(
        elder_id: str,
        request: Request,
        consented_by: str = "",
        auth: GuardianAuth = Depends(current_guardian),
    ) -> dict:
        """上傳參考音檔，設定（或覆蓋）這位長輩的專屬聲音。

        body 為**原始音檔 bytes**（與 `/turns` 同一個慣例，不用 multipart）；
        `consented_by` 走 query param，因為 body 已經被音檔佔滿。

        PUT 而非 POST：一位長輩只有一組生效聲音（`voice_profiles` 的 PK 就是
        elder_id），重錄即覆蓋，語意是冪等的取代而不是新增第 N 筆。
        """
        scope.assert_manages(auth, elder_id)
        _require_enabled()

        # 同意留痕必填（與 D-13 的 consents 表同一把尺）：這是**別人的聲音**，
        # 要被系統拿去對所有跟這位長輩的對話說話。沒有人明確同意就不該建立。
        consent = consented_by.strip()
        if not consent:
            raise HTTPException(status_code=400, detail=ErrorCode.CONSENT_REQUIRED)

        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("audio/"):
            raise HTTPException(status_code=415, detail=ErrorCode.UNSUPPORTED_MEDIA_TYPE)
        audio = await request.body()
        if not audio:
            raise HTTPException(status_code=400, detail=ErrorCode.MISSING_AUDIO)
        if len(audio) > _MAX_REFERENCE_BYTES:
            raise HTTPException(status_code=413, detail=ErrorCode.AUDIO_TOO_LARGE)

        try:
            path = publisher.upload_voice_reference(elder_id, audio, content_type=content_type)
        except AudioPublishError as exc:
            # 上傳失敗不寫設定檔：寫了就會指向一個不存在的物件，之後每一輪都要
            # 走一次「下載失敗→退回全域預設」，而家屬那端以為已經設定好了。
            raise HTTPException(status_code=502, detail=ErrorCode.SPEECH_UNAVAILABLE) from exc

        try:
            voice_profiles.save(
                VoiceProfile(
                    elder_id=elder_id,
                    prompt_audio_path=path,
                    # 逐字稿＝系統下發的那份稿子。家屬照唸，所以這裡不必猜、也不必辨識。
                    prompt_text=VOICE_PROFILE_SCRIPT,
                    consented_by=consent,
                    granted_at=clock().timestamp(),
                    revoked_at=None,
                )
            )
        except VoiceProfileError as exc:
            # 音檔已上傳但設定檔沒寫成：不謊報成功。家屬重試會覆蓋同一個路徑
            # （`upload_voice_reference` 用 upsert），不會留下垃圾。
            raise HTTPException(status_code=503, detail=ErrorCode.SPEECH_UNAVAILABLE) from exc

        return ok({"elder_id": elder_id, "has_profile": True, "consented_by": consent})

    @router.delete("/elders/{elder_id}/voice-profile", status_code=204)
    def revoke_voice_profile(elder_id: str, auth: GuardianAuth = Depends(current_guardian)) -> None:
        """撤銷客製化聲音，下一輪起回到全域預設的金孫聲音。

        ⚠️ 只寫 `revoked_at`、不刪 bucket 裡的音檔：撤銷要能立即生效（下一輪就回
        預設聲音），而刪檔是可能失敗的外部呼叫。讓「聲音不再被使用」取決於一次
        資料庫寫入，比取決於一次網路請求可靠。實際刪除另由保留政策處理。
        """
        scope.assert_manages(auth, elder_id)
        _require_enabled()
        voice_profiles.revoke(elder_id, revoked_at=clock().timestamp())

    return router
