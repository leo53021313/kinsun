"""App 對講機通道：POST /turns——上傳錄音，同一回應回傳文字＋回覆音檔 URL。

prefix 由組裝處統一指定（✅ D-28）。

與 channels/line/ 平行的第二通道 adapter：HTTP 請求正規化成
InboundMessage(Channel.APP, …) 進既有 dispatch——閘門（同意複核）、危急偵測、
記憶、觀測、語音回覆全部重用；reply／reply_voice 為收集器，dispatch 結束後
轉成 JSON 回應（同步請求／回應，無 LINE 的 webhook／reply 兩段式）。

⚠️ 容量閘門（spec 2026-07-30 §10 B2）：與 `ws.py` 共用同一個 `TurnAdmission`
物件（由 `app.py` 建立並分別注入兩條路徑），滿載時排隊、逾時回 503——沿用
`ws.py` 的 `_BUSY_REPLY` 文案，兩條路徑對長輩說的話不該有兩種版本。
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from kinsun.accounts.models import Channel, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.channels.app.admission import AdmissionTimeout, TurnAdmission
from kinsun.channels.app.inbound_audio import start_inbound_upload
from kinsun.channels.app.ws import _BUSY_REPLY, _DEFAULT_TURN_CONCURRENCY
from kinsun.channels.inbound import InboundMessage, dispatch
from kinsun.locations.store import ElderLocation, is_valid_coordinate, is_valid_place
from kinsun.turn_context import transcript_listener
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode
from kinsun.web.routers.deps import strip_bearer

logger = logging.getLogger("kinsun.channels.app")

_DEFAULT_MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 對講機單回合上限預設 10MB（✅ D-26 env 可調）


class _NullBinding:
    """App 無文字選單流程：handle 一律回 None。"""

    def handle(self, external_id: str, text: str) -> None:
        return None


class _TurnCollector:
    """收集 dispatch 的回覆：文字與（若有）公開音檔 URL。"""

    def __init__(self) -> None:
        self.transcript = ""
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

    def record_transcript(self, text: str) -> None:
        self.transcript = text


def create_app_turns_router(
    *,
    accounts: AccountService,
    pipeline,
    gate,
    voice,
    traces=None,
    inbound_audio=None,
    new_id: Callable[[], str] | None = None,
    locations=None,
    clock: Callable[[], datetime] | None = None,
    max_audio_bytes: int = _DEFAULT_MAX_AUDIO_BYTES,
    admission: TurnAdmission | None = None,
    rate_limiter=None,
) -> APIRouter:
    router = APIRouter(tags=["turns"])
    make_id = new_id or (lambda: uuid.uuid4().hex)
    now = clock or (lambda: datetime.now(UTC))
    # ⚠️ 刻意不叫 `gate`：本函式的 `gate` 參數是 `ConsentGate`（同意複核），命名
    # 相撞會讓 dispatch 的 `gate=gate` 悄悄改傳錯物件。與 `ws.py` 同一顆
    # `TurnAdmission`（由 `app.py` 建立並分別注入兩條路徑）才擋得住「同一時間
    # 兩條路徑合計超過容量」；各自建一個的話，兩條路徑可以互相繞過對方的閘門。
    turn_gate = admission or TurnAdmission(_DEFAULT_TURN_CONCURRENCY)

    def _save_location(elder_id: str, place: str, lat: float | None, lon: float | None) -> None:
        """記下長輩這輪回報的地點與模糊座標（約 0.01 度／1.1 公里，手機端已捨去精度）。

        三者必須同時具備才寫入：只有地名沒座標（或反之）視同「這輪沒有位置」。
        App 要嘛三個都給、要嘛都不給；接受半套只會讓下游多一條沒人走的分支。

        空字串／純空白的地名＝「這輪沒有位置」（未授權、室內收不到），**不是**
        「他不在任何地方」——故不寫入也不清空既有資料。
        """
        # 地名太長＝這輪沒有位置（V-05，2026-07-29）：2 萬字的地名會原樣落庫，而且
        # **每一輪都注入提示詞**——既燒 token，也是提示注入的入口。判準與 WS 共用。
        if locations is None or not is_valid_place(place) or lat is None or lon is None:
            return
        place = place.strip()
        # 座標超出地表範圍＝這輪沒有位置（V-04，2026-07-29）。⚠️ 刻意**不**寫成
        # FastAPI 簽章的 `Query(ge=-90, le=90)`：那會回 422，連長輩那句話一起退掉。
        # 位置是加分項（見下方 except 的註解），為了 App 送錯一個參數而讓長輩重講
        # 一次，代價遠大於少一筆位置。
        if not is_valid_coordinate(lat, lon):
            logger.warning("長輩地點座標超出範圍，這輪不寫入")
            return
        try:
            locations.save(ElderLocation(elder_id, place, now().timestamp(), lat, lon))
        except Exception:  # noqa: BLE001 - 位置是加分項，寫入失敗不可中斷對話
            logger.warning("長輩地點寫入失敗")

    def current_elder(authorization: str = Header(default="")) -> str:
        token = strip_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail=ErrorCode.MISSING_TOKEN)
        auth = accounts.authenticate_token(token)
        if auth is None or auth.principal_type is not PrincipalType.ELDER:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN)
        return auth.principal_id

    @router.post("/turns", status_code=201)
    async def create_turn(
        request: Request,
        location: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        elder_id: str = Depends(current_elder),
    ) -> dict:
        # 往返延遲起點（✅ D-05 戊-2）：請求進入處理的時刻，與 dispatch 的預設
        # timer（time.monotonic）同源；涵蓋收音檔、進站上傳與整段管線。
        received_at = time.monotonic()
        # token 不代表同意：撤回或綁定消失即擋（閘門以 (channel, external_id) 複核）。
        external_id = accounts.app_external_id_of_elder(elder_id)
        if external_id is None or gate.resolve_elder(Channel.APP, external_id) is None:
            raise HTTPException(status_code=403, detail=ErrorCode.CONSENT_REVOKED)
        # content-type 驗證（✅ D-61 丙-11）：只收音訊，擋誤傳的 JSON／文字。
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("audio/"):
            raise HTTPException(status_code=415, detail=ErrorCode.UNSUPPORTED_MEDIA_TYPE)
        audio = await request.body()
        if len(audio) > max_audio_bytes:
            raise HTTPException(status_code=413, detail=ErrorCode.AUDIO_TOO_LARGE)
        # 每位長輩的保險絲（spec 2026-07-30 §10 B2）：純粹防前端 bug（重連迴圈狂送），
        # 對真人操作等同無限，走到這裡幾乎一定是程式在打自己。排在容量閘門之前——
        # 被擋下的這一輪不該去佔用容量閘門的名額。
        if rate_limiter is not None and not rate_limiter.hit(f"turn:{elder_id}"):
            logger.warning("長輩輪數超過每分鐘上限 elder=%s", elder_id)
            raise HTTPException(
                status_code=429,
                detail={"code": ErrorCode.TOO_MANY_REQUESTS, "message": _BUSY_REPLY},
            )

        def _run_with_admission() -> dict:
            # ⚠️ 在執行緒池裡取名額：這個 handler 是 async 的，在事件迴圈上阻塞
            # 等待會讓**所有人**的請求一起停住——包含那些根本沒有要用對講機的。
            #
            # ⚠️ 這裡的名額涵蓋範圍與 `ws.py` **刻意不同**：`ws.py::_run_turn` 只把
            # `dispatch(...)` 包進閘門，`_save_location`／`start_inbound_upload`
            # 等非 GPU 工作留在閘門外——那份 docstring 講的理由是「提早佔位只會讓
            # 排隊位置變得不誠實」。但 POST 這條路徑**沒有** `queued` 訊框可以回報
            # 排隊位置（逾時前只會靜默等待，成功／逾時才各自回一次），故「位置不
            # 誠實」這個顧慮本來就不適用；而 `_save_location`（一次 DB 寫入）與
            # `start_inbound_upload`（背景起執行緒，近乎立即返回）都不是耗時操作，
            # 讓它們留在整個 `_run_turn` 裡（含在名額涵蓋範圍內）換來程式碼不必為了
            # 對齊 ws.py 而把 `_run_turn` 拆成「閘門前／閘門內」兩段——後者是更大幅
            # 的重構，風險高於這裡的些微時間差。
            with turn_gate.admit():
                return _run_turn(
                    audio=audio,
                    elder_id=elder_id,
                    external_id=external_id,
                    location=location,
                    latitude=latitude,
                    longitude=longitude,
                    received_at=received_at,
                )

        # ⚠️ 一定要交給執行緒池：底下整段（進站上傳、ASR、Gemini、TTS、落庫）全是
        # 同步阻塞呼叫，留在 async handler 裡就是佔住事件迴圈。實測（2026-07-26 全流程
        # 模擬）一輪對話進行中，連 GET /healthz 都要等 2.89 秒——整台後端一次只服務得了
        # 一位長輩，第二位開口就得排隊，家屬 App 與後台也一起卡住。FastAPI 對所有同步
        # handler 本來就是這樣跑的，這裡只是把這支端點放回同一條路上。
        try:
            result = await run_in_threadpool(_run_with_admission)
        except AdmissionTimeout:
            # 長輩看不懂 429。回既有的婉拒文案，與 WS 路徑同一句——兩條路徑對長輩
            # 說的話不該有兩種版本。
            logger.warning("排隊逾時，婉拒這一輪 elder=%s", elder_id)
            raise HTTPException(
                status_code=503,
                detail={"code": ErrorCode.TOO_MANY_REQUESTS, "message": _BUSY_REPLY},
            ) from None
        return ok(result)

    def _run_turn(
        *,
        audio: bytes,
        elder_id: str,
        external_id: str,
        location: str,
        latitude: float | None,
        longitude: float | None,
        received_at: float,
    ) -> dict:
        """一輪對話的同步本體（在工作執行緒裡跑）。順序與拆出前一字不差。"""
        # ⚠️ 必須排在 dispatch 之前：長輩這句話問的就是天氣時，這一輪就得用得到；
        # 排在後面等於永遠慢一輪——而「慢一輪」在對講機上的表現就是他問第一次
        # 還是被反問，功能等於沒做。
        _save_location(elder_id, location, latitude, longitude)
        trace_id = make_id()
        # 背景上傳，不等網址：見 `channels/app/inbound_audio.py`（延遲優化 B1）。
        start_inbound_upload(inbound_audio, traces, audio, trace_id)
        collector = _TurnCollector()
        msg = InboundMessage(
            Channel.APP,
            external_id,
            "audio",
            "",
            audio,
            collector.reply,
            collector.reply_voice,
            trace_id=trace_id,
            audio_url="",
            received_at=received_at,
        )
        with transcript_listener(collector.record_transcript):
            outcome = dispatch(
                msg,
                pipeline=pipeline,
                binding=_NullBinding(),
                gate=gate,
                voice=voice,
                traces=traces,
                elder_id=elder_id,  # 入口已解析並複核同意，dispatch 不再重查（✅ 庚-12）
            )
        chunk_count = outcome.chunk_count if outcome else 0
        return {
            "transcript": collector.transcript,
            "text": collector.text,
            "audio_url": collector.audio_url,
            "duration_ms": collector.duration_ms,
            # 這條 REST 路徑恆為 0：分段只在 `turn_context.is_inline_audio_delivery()`
            # 為 True 時才成立（見 `pipeline._synthesize`），而這裡建的 `InboundMessage`
            # 沒有帶 `reply_audio`，該旗標恆 False。多段語音改由 WS 通道逐段推播
            # （`ws.py::_push_continuation_chunks`，2026-08-01），這個欄位留著只是
            # 讓回應形狀與 WS 路徑一致，不代表這條 POST 路徑會分段。
            "chunk_count": chunk_count,
            "reply_digest": outcome.reply_digest if outcome else "",
        }

    return router
