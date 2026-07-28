"""App 對講機的 WebSocket 通道：整輪對話走同一條長連線（spec 2026-07-28 P2）。

## 為什麼整輪都走它，而不是只加一條下行通道

非同步回覆要讓後端**主動**送第二則訊息（先「稍等我喔」、答案好了再送）。後端正式模式
跑兩個 worker（`WEB_WORKERS` 預設 2），連線由作業系統分派——若錄音照舊走
`POST /turns`、只另外加一條下行 WebSocket，長輩的連線可能握在 worker A、他的錄音卻
落在 worker B，**算出答案的那個推不出去**。整輪同一條連線讓歸屬問題自動消失，
不必新增任何基礎設施（Redis／LISTEN NOTIFY），也不必退回單 worker。

額外紅利：同一位長輩的所有併發輪必然在同一條連線、同一個 worker 底下，P3 的
「在途清單」可以直接掛在連線物件上。

## 協定

上行：
- 一個 **binary** 訊息 ＝ 一輪完整音檔（不做串流錄音——ASR 目前是整檔 API，
  改串流是獨立工程）。
- 一個 **JSON** 訊息可先送位置：`{"location": "…", "latitude": …, "longitude": …}`。
  它只更新「下一輪要用的位置」，不自成一輪。

下行（皆帶 `turn_id`）：
- `ack`——模型決定要查東西時。欄位：`text`、`audio_url`、`duration_ms`
- `reply`——答案算完。欄位：`text`、`audio_url`、`duration_ms`、`chunk_count`、`reply_digest`
- `error`——任一段失敗。欄位：`text`（回退話術）

`POST /turns` 保留不動：LINE 通道仍走 `dispatch`，且 WebSocket 連不上時必須有降級路徑。

## 兩個非做不可的實作要點

⚠️ **收到音檔立刻交給執行緒池**，不可在讀迴圈裡跑完整輪。底下整段（ASR、Gemini、
TTS、落庫）全是同步阻塞呼叫，留在讀迴圈裡等於長輩在等答案時的第二次發話根本讀不進來
——P3 的併發對話會直接失效。這與 `turns.py` 的 `run_in_threadpool` 是同一個教訓。

⚠️ **從工作執行緒送訊息要跨回事件迴圈**：`WebSocket.send_json` 是 async 的，而安撫話
與回覆都是在工作執行緒裡產生的。故以 `asyncio.run_coroutine_threadsafe` 交還給迴圈，
並在送出失敗時只留 warning——連線斷了不該讓那一輪的落庫與記憶寫入跟著炸掉。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from kinsun.accounts.models import Channel, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.agent import SYSTEM_TROUBLE_REPLY
from kinsun.channels.inbound import InboundMessage, dispatch
from kinsun.locations.store import ElderLocation
from kinsun.turn_context import tool_announcer

logger = logging.getLogger("kinsun.channels.app.ws")

_DEFAULT_MAX_AUDIO_BYTES = 10 * 1024 * 1024

# 關閉碼。1008＝policy violation，用於認證與同意複核失敗。
_CLOSE_UNAUTHORIZED = 1008


class _NullBinding:
    """App 無文字選單流程：handle 一律回 None（與 `turns.py` 相同）。"""

    def handle(self, external_id: str, text: str) -> None:
        return None


class _TurnCollector:
    """收集 dispatch 的回覆：文字與（若有）公開音檔 URL（與 `turns.py` 相同）。"""

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


class _Sender:
    """從工作執行緒把訊息送回 WebSocket。

    ⚠️ 送出失敗只留 warning、不往外拋：連線在對話進行中斷掉是常態（長輩走出訊號範圍、
    App 被切到背景），而那一輪的落庫與記憶寫入不該跟著炸掉。
    """

    def __init__(self, websocket: WebSocket, loop: asyncio.AbstractEventLoop) -> None:
        self._websocket = websocket
        self._loop = loop

    def send(self, payload: dict) -> None:
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._websocket.send_json(payload), self._loop
            )
            future.result(timeout=5)
        except Exception:  # noqa: BLE001 - 連線斷掉不可中斷那一輪的其餘工作
            logger.warning("WebSocket 送出失敗 type=%s", payload.get("type"))


def create_app_ws_router(
    *,
    accounts: AccountService,
    pipeline,
    gate,
    voice,
    traces=None,
    inbound_audio=None,
    ack_audio=None,
    locations=None,
    new_id: Callable[[], str] | None = None,
    clock: Callable[[], datetime] | None = None,
    max_audio_bytes: int = _DEFAULT_MAX_AUDIO_BYTES,
) -> APIRouter:
    router = APIRouter(tags=["turns"])
    make_id = new_id or (lambda: uuid.uuid4().hex)
    now = clock or (lambda: datetime.now(UTC))

    def _resolve_elder(token: str) -> tuple[str, str] | None:
        """token → (elder_id, external_id)；認證或同意複核失敗回 None。

        與 `turns.py` 的 `current_elder` ＋ 同意複核等價——**閘門不可省**：
        token 不代表同意，撤回或綁定消失即擋。
        """
        auth = accounts.authenticate_token(token) if token else None
        if auth is None or auth.principal_type is not PrincipalType.ELDER:
            return None
        external_id = accounts.app_external_id_of_elder(auth.principal_id)
        if external_id is None or gate.resolve_elder(Channel.APP, external_id) is None:
            return None
        return auth.principal_id, external_id

    def _save_location(elder_id: str, place: str, lat, lon) -> None:
        """記下長輩回報的地點（與 `turns.py` 的 `_save_location` 同一套規則）。

        三者必須同時具備才寫入；空地名＝「這輪沒有位置」，不寫入也不清空既有資料。
        """
        place = (place or "").strip()
        if locations is None or not place or lat is None or lon is None:
            return
        try:
            locations.save(
                ElderLocation(elder_id, place, now().timestamp(), float(lat), float(lon))
            )
        except Exception:  # noqa: BLE001 - 位置是加分項，寫入失敗不可中斷對話
            logger.warning("長輩地點寫入失敗")

    def _publish_inbound(audio: bytes) -> str:
        if inbound_audio is None:
            return ""
        try:
            return inbound_audio.publish(audio, content_type="audio/m4a")
        except Exception:  # noqa: BLE001 - 上傳失敗不可中斷對話
            logger.warning("App 進站音檔上傳失敗")
            return ""

    def _ack_sender(sender: _Sender, turn_id: str) -> Callable[[list[str]], None]:
        """做出「模型決定要查什麼」時要跑的那件事：挑一句安撫話立刻送出去。

        ⚠️ 這裡**不合成、不上傳**——音檔在啟動時就備好了（見 `speech/ack_audio.py`）。
        現場合成一句 10 字的安撫話要 1.86 秒，等於把這個功能省下來的延遲還掉快一半。
        """

        def announce(tool_names: list[str]) -> None:
            if ack_audio is None:
                return
            clip = ack_audio.clip_for(tool_names[0])
            if clip is None:  # 還沒暖好或簽章過期＝這輪不講（降級不是錯誤）
                return
            sender.send(
                {
                    "type": "ack",
                    "turn_id": turn_id,
                    "text": clip.text,
                    "audio_url": clip.audio_url,
                    "duration_ms": clip.duration_ms,
                }
            )

        return announce

    def _run_turn(
        *,
        sender: _Sender,
        audio: bytes,
        elder_id: str,
        external_id: str,
        turn_id: str,
        received_at: float,
    ) -> None:
        """一輪對話的同步本體（在工作執行緒裡跑）。

        流程與 `turns.py::_run_turn` 一致，差別只在：回覆用 `sender` 推出去而不是
        當成 HTTP 回應，且中途多一則安撫話。
        """
        collector = _TurnCollector()
        msg = InboundMessage(
            Channel.APP,
            external_id,
            "audio",
            "",
            audio,
            collector.reply,
            collector.reply_voice,
            trace_id=turn_id,
            audio_url=_publish_inbound(audio),
            received_at=received_at,
        )
        try:
            with tool_announcer(_ack_sender(sender, turn_id)):
                outcome = dispatch(
                    msg,
                    pipeline=pipeline,
                    binding=_NullBinding(),
                    gate=gate,
                    voice=voice,
                    traces=traces,
                    elder_id=elder_id,  # 入口已解析並複核同意（✅ 庚-12）
                )
        except Exception:  # noqa: BLE001 - 一輪失敗不可打斷整條連線
            logger.exception("WebSocket 對話輪失敗 turn=%s", turn_id)
            sender.send({"type": "error", "turn_id": turn_id, "text": SYSTEM_TROUBLE_REPLY})
            return
        chunk_count = outcome.chunk_count if outcome else 0
        sender.send(
            {
                "type": "reply",
                "turn_id": turn_id,
                "text": collector.text,
                "audio_url": collector.audio_url,
                "duration_ms": collector.duration_ms,
                "chunk_count": chunk_count,
                "reply_digest": outcome.reply_digest if outcome else "",
            }
        )

    @router.websocket("/ws/talk")
    async def talk(websocket: WebSocket) -> None:
        # token 走 query string：WebSocket 握手在瀏覽器與 React Native 都不能自訂
        # Authorization 標頭（`expo` 的 WebSocket 亦然），這是該協定的普遍作法。
        # ⚠️ 因此 token 會進入伺服器的存取日誌——`logging_setup` 不記 query string，
        # 但反向代理可能會，部署時須留意。
        token = websocket.query_params.get("token", "")
        resolved = _resolve_elder(token)
        if resolved is None:
            await websocket.close(code=_CLOSE_UNAUTHORIZED)
            return
        elder_id, external_id = resolved
        await websocket.accept()
        loop = asyncio.get_running_loop()
        sender = _Sender(websocket, loop)
        pending: dict = {}  # 下一輪要用的位置（由 JSON 訊息帶入）
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                text = message.get("text")
                if text is not None:
                    pending = _parse_location(text)
                    continue
                audio = message.get("bytes")
                if not audio:
                    continue
                received_at = time.monotonic()
                if len(audio) > max_audio_bytes:
                    sender.send({"type": "error", "turn_id": "", "text": SYSTEM_TROUBLE_REPLY})
                    continue
                # ⚠️ 位置必須排在這一輪之前：長輩這句話問的就是天氣時，這一輪就得用到。
                _save_location(
                    elder_id,
                    pending.get("location", ""),
                    pending.get("latitude"),
                    pending.get("longitude"),
                )
                turn_id = make_id()
                # ⚠️ 一定要丟執行緒池：整輪是同步阻塞的，留在讀迴圈裡就讀不到
                # 長輩等待期間的第二次發話——P3 的併發對話會直接失效。
                # 不 await：這正是「等待中還能繼續講話」的實作方式。
                loop.run_in_executor(
                    None,
                    lambda a=audio, t=turn_id, r=received_at: _run_turn(
                        sender=sender,
                        audio=a,
                        elder_id=elder_id,
                        external_id=external_id,
                        turn_id=t,
                        received_at=r,
                    ),
                )
        except WebSocketDisconnect:
            return

    return router


def _parse_location(raw: str) -> dict:
    """解析上行的位置 JSON；壞掉就當成「這輪沒有位置」。

    外部輸入是資料不是指令：解析失敗只丟掉這一筆，不可讓一則畸形訊息切斷長輩的連線。
    """
    import json

    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning("WebSocket 位置訊息不是合法 JSON，忽略")
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "location": payload.get("location", ""),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
    }
