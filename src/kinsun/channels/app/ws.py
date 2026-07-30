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
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from kinsun.accounts.models import Channel, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.agent import SYSTEM_TROUBLE_REPLY
from kinsun.channels.inbound import InboundMessage, dispatch
from kinsun.locations.store import ElderLocation, is_valid_coordinate, is_valid_place
from kinsun.turn_context import (
    pending_utterances,
    tool_announcer,
    transcript_listener,
    turn_directive,
)

logger = logging.getLogger("kinsun.channels.app.ws")

_DEFAULT_MAX_AUDIO_BYTES = 10 * 1024 * 1024

# 關閉碼。1008＝policy violation，用於認證與同意複核失敗。
_CLOSE_UNAUTHORIZED = 1008

# 同時在跑的輪數上限（spec 2026-07-28 P3）。
#
# 長輩連按麥克風會開出無限多輪，每一輪都佔一條執行緒、一組 Gemini 呼叫與一次 TTS。
# 無上限的代價與 `background.py` 的佇列上限同源：撐爆行程比少回一句嚴重得多。
# 3 是「連問三件事還撐得住」與「不失控」之間的取捨——實測長輩的自然節奏是一次一件，
# 併發兩輪已經是少見情形。
_MAX_CONCURRENT_TURNS = 3
_BUSY_REPLY = "金孫還在忙前面那幾句，等一下下再跟您說好嗎？"

# 晚到答案的回指指示。⚠️ 走系統提示而不是程式層硬前綴——拼接出來的句子 TTS 唸起來
# 會斷裂，而這句話要讓長輩覺得是金孫自己想起來的。
_LATE_REPLY_DIRECTIVE = (
    "（系統提示）長輩問完這句之後又講了別的，所以這個答案是慢了幾句才回來的。"
    "開頭請自然帶一句回指，讓他知道你在回哪一個問題"
    "（例如「對了，您剛剛問的那個喔」），不要突兀地直接講答案。"
)


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


class _InFlight:
    """這條連線上還在跑的輪（spec 2026-07-28 P3）。

    ⚠️ 掛在**連線**上而不是全域：整輪走同一條 WebSocket，所以同一位長輩的所有併發輪
    必然在同一條連線、同一個 worker 底下——這正是「整輪走 WebSocket」換來的紅利，
    不需要任何跨進程機制。

    只存在記憶體、被濫用審核攔下的輪直接丟棄，故不違反「被攔的輪不進記憶」的安全契約。
    """

    def __init__(self) -> None:
        self._turns: dict[str, str] = {}  # turn_id → 長輩的原話（ASR 之後才有）
        self._order: list[str] = []  # 依開口順序，用來判斷誰是最新的一輪
        self._lock = threading.Lock()

    def start(self, turn_id: str) -> bool:
        """登記一輪；超過上限回 False（呼叫端據此回一句「還在忙」）。"""
        with self._lock:
            if len(self._order) >= _MAX_CONCURRENT_TURNS:
                return False
            self._turns[turn_id] = ""
            self._order.append(turn_id)
            return True

    def set_utterance(self, turn_id: str, text: str) -> None:
        with self._lock:
            if turn_id in self._turns:
                self._turns[turn_id] = text

    def finish(self, turn_id: str) -> None:
        with self._lock:
            self._turns.pop(turn_id, None)
            if turn_id in self._order:
                self._order.remove(turn_id)

    def others(self, turn_id: str) -> list[str]:
        """其他還在跑的輪，長輩講過的話（依開口順序，排除自己與尚未辨識完的）。"""
        with self._lock:
            return [
                self._turns[other]
                for other in self._order
                if other != turn_id and self._turns.get(other)
            ]

    def is_latest(self, turn_id: str) -> bool:
        """這一輪是不是長輩最後講的那一句——不是就代表答案晚到了，回覆要帶回指。"""
        with self._lock:
            return not self._order or self._order[-1] == turn_id


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
        # 地名太長＝這輪沒有位置（V-05，2026-07-29）：判準與 REST 共用，見 locations/store。
        if locations is None or not is_valid_place(place) or lat is None or lon is None:
            return
        place = place.strip()
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
        in_flight: _InFlight,
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
        # 晚到回指（spec P3）：長輩在這一輪還沒回來之前又講了別的，答案回去時
        # 要讓他知道在回哪一個問題。判斷點在**開跑前**——那時已經知道自己是不是
        # 最新的一輪，而系統提示必須在 LLM 呼叫之前就備好。
        directive = "" if in_flight.is_latest(turn_id) else _LATE_REPLY_DIRECTIVE
        try:
            with (
                tool_announcer(_ack_sender(sender, turn_id)),
                transcript_listener(lambda text: in_flight.set_utterance(turn_id, text)),
                pending_utterances(lambda: in_flight.others(turn_id)),
                turn_directive(directive),
            ):
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
        finally:
            # ⚠️ 一定要在 finally：這一輪失敗時若沒有解除登記，名額會一直被佔著，
            # 長輩問滿三次之後就再也得不到回應。
            in_flight.finish(turn_id)
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
        in_flight = _InFlight()
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
                if not in_flight.start(turn_id):
                    # 連按太多次：回一句「還在忙」而不是靜默丟掉，長輩才知道發生什麼事。
                    logger.warning("併發輪達上限，婉拒這一輪 elder=%s", elder_id)
                    sender.send({"type": "error", "turn_id": turn_id, "text": _BUSY_REPLY})
                    continue
                # ⚠️ 一定要丟執行緒池：整輪是同步阻塞的，留在讀迴圈裡就讀不到
                # 長輩等待期間的第二次發話——P3 的併發對話會直接失效。
                # 不 await：這正是「等待中還能繼續講話」的實作方式。
                loop.run_in_executor(
                    None,
                    lambda a=audio, t=turn_id, r=received_at: _run_turn(
                        sender=sender,
                        in_flight=in_flight,
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

    ⚠️ 型別必須在這裡擋（V-03，2026-07-29）：`_save_location` 的 `place.strip()`
    在它自己的 try 之外，地名傳成數字會拋 AttributeError 一路冒到讀迴圈——那裡只接
    `WebSocketDisconnect`，於是**整條連線被砍、且不送任何 error 訊框**。
    最陰險的是發作時機：位置訊框只是存進 `pending`，要等長輩**下一次開口**送音檔
    才會用到，所以症狀是「講完一整句話，連線斷掉，那句話也沒進庫」。只要 App 某個
    版本把 `location` 送成數字，該版本**所有使用者**的第一句話都會斷線。
    REST 那條路因 FastAPI 強制轉字串不受影響，只有 WS 這條主路徑中招。

    三者型別任一不合就整筆丟掉，不接受半套——反正 `_save_location` 本來就要求
    三者齊備，留半筆只是讓「這輪沒有位置」多一種說法。
    """
    import json

    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning("WebSocket 位置訊息不是合法 JSON，忽略")
        return {}
    if not isinstance(payload, dict):
        return {}
    location = payload.get("location", "")
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    # ⚠️ 「沒帶座標」要與「帶了但不合法」分開：前者是既有的正常語意（只送地名＝這輪
    # 沒有位置），把它也記成 warning 等於製造誤導性日誌——那正是讓下一個人查錯方向
    # 的東西。
    if latitude is None and longitude is None:
        return {}
    if not isinstance(location, str) or not is_valid_coordinate(latitude, longitude):
        logger.warning("WebSocket 位置訊框欄位不合法（型別或範圍），整筆忽略")
        return {}
    return {"location": location, "latitude": latitude, "longitude": longitude}
