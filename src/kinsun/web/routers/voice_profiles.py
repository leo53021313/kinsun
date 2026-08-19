"""長輩客製化聲音設定檔：家屬錄一段照唸的參考語音，長輩往後就聽到那個聲音。

與 `voice_profiles/store.py` 的分工：本檔是 HTTP 邊界（權限、驗證、音檔上傳），
持久層與領域模型在該套件裡。

⚠️ 為什麼「錄音內容」是系統給的固定稿（`voice_profiles/script.py`）而不是自由發揮：
CosyVoice zero-shot 要「參考音檔 ＋ 那段音檔的逐字稿」成對輸入，逐字稿一旦對不上
音檔，合成品質就壞掉且無聲無息。固定稿讓逐字稿**不是猜出來的**，同時把
`services/tts/README.md` 那四條錄製準則從「靠人自律」變成內建。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from kinsun.audio.publisher import AudioPublishError
from kinsun.speech.tts import VoiceReference
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

logger = logging.getLogger("kinsun.web.voice_profiles")

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
    ack_audio=None,
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

        granted_at = clock().timestamp()
        try:
            voice_profiles.save(
                VoiceProfile(
                    elder_id=elder_id,
                    prompt_audio_path=path,
                    # 逐字稿＝系統下發的那份稿子。家屬照唸，所以這裡不必猜、也不必辨識。
                    prompt_text=VOICE_PROFILE_SCRIPT,
                    consented_by=consent,
                    granted_at=granted_at,
                    revoked_at=None,
                )
            )
        except VoiceProfileError as exc:
            # 音檔已上傳但設定檔沒寫成：不謊報成功。家屬重試會覆蓋同一個路徑
            # （`upload_voice_reference` 用 upsert），不會留下垃圾。
            raise HTTPException(status_code=503, detail=ErrorCode.SPEECH_UNAVAILABLE) from exc

        _prewarm_ack_batch(elder_id, path, granted_at)
        return ok({"elder_id": elder_id, "has_profile": True, "consented_by": consent})

    def _prewarm_ack_batch(elder_id: str, path: str, granted_at: float) -> None:
        """家屬錄完的當下就用新聲音預錄安撫話（Leo 2026-08-19 需求追加）。

        原本這批要等長輩**第一次開口**才開始暖（`ws.py` 的 `ensure_warm`），整批約
        半分鐘——長輩第一場對話的過場語全趕不上。錄完就開暖的話，家屬把手機拿給
        長輩之前多半已經好了。

        ⚠️ 丟背景執行緒、任何失敗只記 warning：預熱是加分項，簽章或合成失敗都不可
        影響「設定成功」這個既成事實（設定檔已寫入，對話與續段的聲音已經會換新）。
        ⚠️ 只暖得到**收到這次 PUT 的 worker**：快取是行程內的（`WEB_WORKERS` 預設 2），
        另一個 worker 仍靠長輩開口時的 `ensure_warm` 補上——兩條路互為備援，缺一個
        都會讓某些第一場對話沒有過場語。
        """
        if ack_audio is None:
            return

        def _warm() -> None:
            version = str(granted_at)
            try:
                url = publisher.signed_url_for(path, version)
            except Exception:  # noqa: BLE001 - 簽章失敗只影響預熱，設定本身已成功
                logger.warning(
                    "錄後預熱簽章失敗，安撫話批次改由長輩首輪對話觸發 elder_id=%s",
                    elder_id,
                    exc_info=True,
                )
                return
            ack_audio.ensure_warm(
                VoiceReference(
                    elder_id=elder_id,
                    prompt_audio_url=url,
                    prompt_text=VOICE_PROFILE_SCRIPT,
                    version=version,
                )
            )

        threading.Thread(target=_warm, name="kinsun-ack-warm-on-set", daemon=True).start()

    @router.delete("/elders/{elder_id}/voice-profile", status_code=204)
    def revoke_voice_profile(elder_id: str, auth: GuardianAuth = Depends(current_guardian)) -> None:
        """撤銷客製化聲音，下一輪起回到全域預設聲音。

        ⚠️ **順序不可對調**：先寫 `revoked_at`（撤銷是否生效的唯一權威），成功之後才
        去刪 bucket 裡的音檔。讓「聲音不再被使用」取決於一次資料庫寫入，比取決於一次
        可能失敗的網路請求可靠——資料庫寫失敗就整支 500、家屬會重試；反過來做的話，
        檔案刪了但撤銷沒寫進去，`resolve_voice` 仍會拿它去簽網址，變成每輪下載失敗。

        ⚠️ 刪檔失敗**不影響**本端點回 204：那時聲音已經停用了（設定檔查不到），
        回錯誤只會讓家屬以為沒撤銷成功。孤兒物件記 warning，見
        `delete_voice_reference`。這些是長輩家人的聲紋，不能只標記停用就永遠留著
        ——`cleanup(retention_days)` 掃不到 `voice-refs/`。
        """
        scope.assert_manages(auth, elder_id)
        _require_enabled()
        voice_profiles.revoke(elder_id, revoked_at=clock().timestamp())
        publisher.delete_voice_reference(elder_id)

    return router
