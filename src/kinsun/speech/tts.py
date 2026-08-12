"""TTS 介面與實作。dev 用文字泡泡 placeholder；正式呼叫 DGX 上的 services/tts。

另含 `QueuedTtsClient`——把所有合成請求序列化並依優先權排序的裝飾器，見其 docstring。
"""

from __future__ import annotations

import contextvars
import itertools
import json
import logging
import queue
import threading
from collections.abc import Iterator
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol

from kinsun import tracing
from kinsun.transport import HttpxTransport, Transport, TransportError, header_value

logger = logging.getLogger("kinsun.speech.tts")


class TTSError(Exception):
    """語音合成失敗。"""


@dataclass(frozen=True)
class TtsResult:
    text: str
    audio: bytes | None = None
    duration_ms: int = 0
    transcript: str = ""  # 本輪 ASR 辨識到的長者原話（debug 用，不進語音合成）
    # 分段串流（2026-07-26 延遲優化）：>0 代表 `audio` 只是**第一段**、整段回覆被切成
    # chunk_count 段，其餘由呼叫端另外取（見 speech/chunking.py 與 App 對講機端點）。
    # 0＝沒有分段，`audio` 就是完整回覆（LINE 與所有未啟用分段的通道皆為此值）。
    chunk_count: int = 0


@dataclass(frozen=True)
class VoiceReference:
    """長輩的客製化參考語音（聲音克隆用）；未提供則沿用 DGX 端全域預設聲音。"""

    elder_id: str
    prompt_audio_url: str
    prompt_text: str
    # 這份參考語音的版本（2026-08-12）。DGX 端把下載回來的音檔快取在本機、只認
    # elder_id，於是家屬重錄之後——`PUT` 覆蓋 bucket 內同一個物件路徑、應用層也換發了
    # 簽章網址——DGX 端仍然拿舊檔案合成，直到快取被擠掉或服務重啟。**過程中不會有任何
    # 錯誤訊息**，家屬只會覺得「我明明重錄了怎麼沒變」。
    #
    # ⚠️ 值取自 `voice_profiles.granted_at`（每次 `save` 都換值），**不可**改用簽章網址：
    # 那個網址每小時換發一次，拿它當版本等於每小時強制重新下載，本機快取形同虛設。
    version: str = ""


class TTSClient(Protocol):
    def synthesize(self, text: str, *, voice: VoiceReference | None = None) -> TtsResult: ...


class TextBubbleTts:
    """placeholder：回文字泡泡，不產音檔（audio=None）。"""

    def synthesize(self, text: str, *, voice: VoiceReference | None = None) -> TtsResult:
        return TtsResult(text=text, audio=None)


class DgxTtsClient:
    """正式：POST {"text"} 到 DGX 上的 TTS 服務，取回 m4a bytes 與時長。"""

    def __init__(
        self,
        endpoint: str,
        timeout: float,
        *,
        api_key: str = "",
        transport: Transport | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._api_key = api_key
        self._transport = transport or HttpxTransport()

    def synthesize(self, text: str, *, voice: VoiceReference | None = None) -> TtsResult:
        payload: dict[str, str] = {"text": text}
        if voice is not None:
            payload["elder_id"] = voice.elder_id
            payload["prompt_audio_url"] = voice.prompt_audio_url
            payload["prompt_text"] = voice.prompt_text
            # 少了它，DGX 端就分不出「家屬重錄過了」，見 VoiceReference.version。
            payload["prompt_version"] = voice.version
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:  # 共用金鑰（✅ D-56 丙-10）；未設＝內網開發模式
            headers["X-Api-Key"] = self._api_key
        try:
            response = self._transport.request(
                "POST",
                self._endpoint,
                data=body,
                headers=headers,
                timeout=self._timeout,
            )
        except TransportError as exc:
            raise TTSError(f"DGX TTS 呼叫失敗：{exc}") from exc
        audio = response.body
        raw_ms = header_value(response, "X-Duration-Ms")
        if raw_ms is None:
            raise TTSError("DGX TTS 回應缺少 X-Duration-Ms 標頭")
        try:
            duration_ms = int(raw_ms)
        except ValueError as exc:
            raise TTSError(f"DGX TTS 回應 X-Duration-Ms 非整數：{raw_ms!r}") from exc
        return TtsResult(text=text, audio=audio, duration_ms=duration_ms)


# ── TTS 優先權佇列（spec 2026-07-28 P1）───────────────────────────────────
#
# ⚠️ 為什麼非有不可（2026-07-28 實測，真 TTS 服務打 GB10）：併發合成會互搶 GPU，
# 而且搶得**沒有規律**。同一個工作負載（兩輪各一段短句一段長句）跑兩回合：
#     回合一：1.89s／7.47s／15.08s／13.28s
#     回合二：3.69s／14.89s／1.88s／9.18s
# 同一種段落某次 1.88 秒回來、另一次等了 15.08 秒——排隊完全看誰先搶到。
#
# 序列化在此不是妥協而是**正確的形狀**：長輩一次只能聽一則，所以 TTS 一次只做一則
# 本來就夠。佇列真正買到的是可預測性，不是吞吐量——四段的總完成時間幾乎不變
# （15.08s vs 推算 14.74s），但「長輩多快聽到第一個聲音」從不可預測的 15 秒
# 變成穩定的 3.7 秒。
#
# 這也順帶修掉一個既有問題：夜間排程推播的 TTS 目前會與長輩的即時對話搶同一顆 GPU，
# 而沒有任何機制讓對話優先。


class TtsPriority(IntEnum):
    """數字小＝先做。順序即政策，改動前請先想清楚誰在等。"""

    REPLY = 0  # 長輩的回覆（含分段的第一段）——他正在等這個聲音
    CHUNK = 1  # 後續段落——前一段還在播，還有一點餘裕
    PUSH = 2  # 排程推播（主動關懷、用藥回診提醒）——沒有人正在等
    PREWARM = 3  # 安撫話語庫的啟動預熱——最低，且應該讓路給即時對話


# 走 contextvars 而非改 `TTSClient` 協定，理由與 `llm.py` 的 `_usage_collector`、
# `turn_context` 的原話與帳本完全相同：改協定會波及所有替身與呼叫端，而只有少數
# 呼叫端需要指定優先權。預設 REPLY 是**安全側**——漏標的呼叫端會排在前面而不是
# 被餓死，故既有呼叫端（`pipeline._synthesize`）不必改一行就有正確行為。
_priority: contextvars.ContextVar[TtsPriority] = contextvars.ContextVar(
    "kinsun_tts_priority", default=TtsPriority.REPLY
)


@contextmanager
def tts_priority(priority: TtsPriority) -> Iterator[None]:
    """在範圍內宣告這些合成請求的優先權。"""
    token = _priority.set(priority)
    try:
        yield
    finally:
        _priority.reset(token)


def current_tts_priority() -> TtsPriority:
    return _priority.get()


class QueuedTtsClient:
    """把任何 `TTSClient` 包成「一次只跑一個推論、依優先權排序」的客戶端。

    對 `TTSClient` 協定無感：`TextBubbleTts` 與所有測試替身都可以被包，也都可以不包。
    未包裝時行為與本功能之前一字不差，故單元測試與 CLI 不受影響（同 `background.py`
    與 `tracing` 的既有慣例——預設就是原行為，由組裝根決定要不要啟用）。

    ⚠️ 同優先權必須維持先進先出：兩段續段顛倒會讓長輩聽到的話前後對調。
    `PriorityQueue` 對相同優先權沒有順序保證，故每筆帶一個遞增序號當第二鍵。

    ⚠️ worker 是 daemon：行程關閉不被它拖住。要排空請呼叫 `close()`
    （`app.py` 的關機流程負責，比照 `background.shutdown`）。
    """

    def __init__(self, inner: TTSClient) -> None:
        self._inner = inner
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self._closed = False
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._loop, name="kinsun-tts", daemon=True)
        self._worker.start()

    def synthesize(self, text: str, *, voice: VoiceReference | None = None) -> TtsResult:
        if self._closed:  # 關機後仍有人要合成：就地執行，不要靜默丟掉長輩的回覆。
            return self._inner.synthesize(text, voice=voice)
        future: Future = Future()
        # worker 接手的訊號：把「排隊等」與「GPU 在算」切開的那一刀（見下方兩個
        # 等待函式的說明）。
        picked_up = threading.Event()
        # 優先權在**提交當下**取值：worker 執行緒沒有呼叫端的 context。
        self._queue.put(
            (int(current_tts_priority()), next(self._seq), text, voice, future, picked_up)
        )
        self._wait_in_queue(picked_up)
        return self._wait_for_synthesis(future)

    # ⚠️ 為什麼要拆成兩個等待（2026-08-08 觀測盤點）：Opik 原本只有一格 `tts`，
    # 裡面同時包著「排在別人後面等」與「GPU 真的在算」，而這兩者的處置完全不同——
    # 排隊久＝併發超過一顆 GB10 的容量（該調閘門或降併發），合成久＝回覆太長或模型
    # 太慢（該縮字數或改串流）。混成一格，看到「TTS 3 秒」不知道該修哪一個。
    #
    # 兩個等待都跑在**呼叫端**的執行緒，所以 span 會正確巢狀在本輪底下；worker
    # 執行緒沒有呼叫端的 context，在那邊開 span 只會憑空消失。
    @tracing.track(name="tts_queue_wait", type="general", capture_input=False, capture_output=False)
    def _wait_in_queue(self, picked_up: threading.Event) -> None:
        """等 worker 接手。已經輪到時是 0ms（＝沒有人在排隊，正常情形）。"""
        picked_up.wait()

    @tracing.track(name="tts_synthesize", type="general", capture_input=False, capture_output=False)
    def _wait_for_synthesis(self, future: Future) -> TtsResult:
        """等這一段真的算完；inner 的例外原樣重拋（`Future.result` 的既有語意）。"""
        return future.result()

    def _loop(self) -> None:
        while True:
            _priority_value, _seq, text, voice, future, picked_up = self._queue.get()
            try:
                if future is None:  # 收工訊號
                    return
                if future.set_running_or_notify_cancel():
                    # ⚠️ 必須在呼叫 inner **之前**放行排隊那一格，否則兩格會一樣長，
                    # 拆開就失去意義。
                    picked_up.set()
                    future.set_result(self._inner.synthesize(text, voice=voice))
            except BaseException as exc:  # noqa: BLE001 - 原樣交回呼叫端
                future.set_exception(exc)
            finally:
                # ⚠️ 一定要在 finally：future 被取消、或 worker 在 set 之前就炸了時，
                # 呼叫端仍卡在 `picked_up.wait()`——那是一個永遠不會結束的等待，
                # 比少一格觀測嚴重得多。
                if picked_up is not None:
                    picked_up.set()
                self._queue.task_done()

    def close(self) -> None:
        """排空佇列後收工。重複呼叫安全（部署重啟與測試都會走到）。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._queue.join()
        # 收工訊號用最低優先權，確保排在所有已排隊的工作之後。
        # ⚠️ 元數必須與 `synthesize` 放進去的那個 tuple 一致（text／voice／future／
        # picked_up 四項）：`_loop` 是無條件解包，少一個欄位就在關機時炸在解包那行，
        # 而不是走到底下「future 為 None＝收工」的判斷。
        self._queue.put((int(TtsPriority.PREWARM) + 1, next(self._seq), "", None, None, None))
        self._worker.join(timeout=5)


def build_tts_client(settings) -> TTSClient:
    if settings.tts_backend == "dgx":
        if not settings.tts_endpoint:
            raise TTSError("TTS_BACKEND=dgx 但未設定 TTS_ENDPOINT")
        client = DgxTtsClient(
            settings.tts_endpoint, settings.tts_timeout_seconds, api_key=settings.tts_api_key
        )
        # 只有 dgx 後端需要排隊——瓶頸是那顆 GB10。文字泡泡沒有 GPU，包了只是多一層。
        return QueuedTtsClient(client)
    return TextBubbleTts()
