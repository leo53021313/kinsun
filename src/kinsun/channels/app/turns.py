"""App 對講機通道：POST /api/app/turns——上傳錄音，同一回應回傳文字＋回覆音檔 URL。

與 channels/line/ 平行的第二通道 adapter：HTTP 請求正規化成
InboundMessage(Channel.APP, …) 進既有 dispatch——閘門（同意複核）、危急偵測、
記憶、觀測、語音回覆全部重用；reply／reply_voice 為收集器，dispatch 結束後
轉成 JSON 回應（同步請求／回應，無 LINE 的 webhook／reply 兩段式）。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from kinsun.accounts.models import Channel, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.channels.inbound import InboundMessage, dispatch

logger = logging.getLogger("kinsun.channels.app")

_MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 對講機單回合上限 10MB


class _NullBinding:
    """App 無文字選單流程：handle 一律回 None。"""

    def handle(self, external_id: str, text: str) -> None:
        return None


class _TurnCollector:
    """收集 dispatch 的回覆：文字與（若有）公開音檔 URL。"""

    def __init__(self) -> None:
        self.text = ""
        self.audio_url = ""
        self.duration_ms: int | None = None

    def reply(self, text: str) -> None:
        self.text = text

    def reply_voice(self, audio_url: str, duration_ms: int, text: str | None) -> None:
        self.audio_url = audio_url
        self.duration_ms = duration_ms
        if text:
            self.text = text


def create_app_turns_router(
    *,
    accounts: AccountService,
    pipeline,
    gate,
    voice,
    traces=None,
    inbound_audio=None,
    new_id: Callable[[], str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/app")
    make_id = new_id or (lambda: uuid.uuid4().hex)

    def current_elder(authorization: str = Header(default="")) -> str:
        token = authorization.removeprefix("Bearer ").strip()
        auth = accounts.authenticate_token(token) if token else None
        if auth is None or auth.principal_type is not PrincipalType.ELDER:
            raise HTTPException(status_code=401, detail="invalid_token")
        return auth.principal_id

    def _publish_inbound(audio: bytes) -> str:
        if inbound_audio is None:
            return ""
        try:
            return inbound_audio.publish(audio, content_type="audio/m4a")
        except Exception:  # noqa: BLE001 - 上傳失敗不可中斷對話
            logger.warning("App 進站音檔上傳失敗")
            return ""

    @router.post("/turns", status_code=201)
    async def create_turn(request: Request, elder_id: str = Depends(current_elder)) -> dict:
        # token 不代表同意：撤回或綁定消失即擋（閘門以 (channel, external_id) 複核）。
        external_id = accounts.app_external_id_of_elder(elder_id)
        if external_id is None or gate.resolve_elder(Channel.APP, external_id) is None:
            raise HTTPException(status_code=403, detail="consent_revoked")
        audio = await request.body()
        if len(audio) > _MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="audio_too_large")
        collector = _TurnCollector()
        msg = InboundMessage(
            Channel.APP,
            external_id,
            "audio",
            "",
            audio,
            collector.reply,
            collector.reply_voice,
            trace_id=make_id(),
            audio_url=_publish_inbound(audio),
        )
        dispatch(
            msg,
            pipeline=pipeline,
            binding=_NullBinding(),
            gate=gate,
            voice=voice,
            traces=traces,
        )
        return {
            "text": collector.text,
            "audio_url": collector.audio_url,
            "duration_ms": collector.duration_ms,
        }

    return router
