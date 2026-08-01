"""進站音檔的背景上傳（2026-07-30 延遲優化 B1）。

## 為什麼要背景化

這段純粹是留檔用途——`source_audio_url` 除了觀測稽核那一列之外沒有任何消費者
（ASR／agent／TTS 都不讀它，見 `channels.inbound.InboundMessage` docstring），
卻同步擋在 `dispatch` 之前，實測佔 1.3–4.5 秒、比 ASR 本身還久。

## 為什麼用專屬 daemon 執行緒而不是 `background.run`

`background` 那個池只開 2 個 worker，服務對象是本來就快（~0.2 秒）的 DB 寫入。
讓一個 1–4 秒的 HTTP 上傳（以及底下重試用的 `time.sleep`）佔住其中一個，會拖慢
同一輪的其他觀測寫入與提醒標記——這是 `background.py` docstring 既有的紀律。

## 為什麼補寫要重試（2026-07-30 審查 H1）

`record_asr_call`（INSERT）與這裡的 UPDATE 之間**沒有任何順序保證**：INSERT 在
ASR 完成時才送出（實測中位 1.84 秒、GPU 共租下最差 6.3 秒），而上傳約 1–4 秒，
兩個分布大幅重疊；就算入列順序對了，兩者都經 `safe_record` → `background.run`
的 2-worker 佇列，commit 先後仍不保證。上傳較快時 UPDATE 會打在還不存在的列上。

原本的實作不看影響列數，於是「網址永久遺失」與「正常補寫」完全無法區分——而檔案
**已經上傳成功**（佔著 Storage 配額）、`AUDIO_RETENTION_DAYS` 到期照樣刪掉，中間
沒有任何指標指向它。這個網址是 2026-07-18 錄音截斷與 2026-07-29 ASR 幻覺兩次根因
診斷唯一的原始證據來源，值得這幾行重試。

重試用盡才留 warning——重點不只是重試，是**讓「這筆稽核斷了」變成看得見的事實**，
而不是一個沒有人知道的 0 列 UPDATE。
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("kinsun.channels.app")

# 補寫重試的間隔（秒）。首次不等，其後退避；總計最多約 7 秒，足以涵蓋 ASR 最差
# 6.3 秒的實測值。全程在自己的 daemon 執行緒裡，沒有任何人在等。
_RETRY_DELAYS_SECONDS = (0.0, 1.0, 2.0, 4.0)


def attach_source_audio_url(
    traces,
    trace_id: str,
    url: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
    delays: tuple[float, ...] = _RETRY_DELAYS_SECONDS,
) -> bool:
    """把上傳好的網址補回 `asr_calls` 那一列；打不到就退避重試。回傳最終有沒有補上。

    `sleep`／`delays` 是測試注入點（不必真的等）。
    """
    for delay in delays:
        if delay:
            sleep(delay)
        try:
            if traces.update_asr_source_audio_url(trace_id=trace_id, source_audio_url=url):
                return True
        except Exception:  # noqa: BLE001 - 觀測補寫失敗不可影響任何人（已在背景）
            logger.warning("進站音檔網址補寫失敗 trace=%s", trace_id)
            return False
    # 走到這裡代表音檔上傳成功、但 asr_calls 一直沒有那一列可掛（ASR 本身失敗？
    # 或慢到超過重試視窗）。留一行看得見的 warning，不要靜默。
    logger.warning("進站音檔已上傳但 asr_calls 無此列，網址無處可掛 trace=%s", trace_id)
    return False


def start_inbound_upload(inbound_audio, traces, audio: bytes, trace_id: str) -> None:
    """在背景上傳進站音檔並把網址補回觀測列；`inbound_audio` 未設定時整段 no-op。

    ⚠️ 刻意**不**帶 `contextvars.copy_context()` 的 Opik 理由（2026-07-30 審查 L1）：
    本函式的呼叫點在 `dispatch` 之前，而本輪的 root span `care_conversation` 是在
    `channels.inbound._run_pipeline` 才建立——此刻 context 裡沒有任何 span 可繼承，
    `audio_upload` 在 Opik 上本來就是孤兒 root trace（與已移除的 REST 續拉端點
    `turns.py::get_turn_chunk` 過去修掉的那個既有缺陷同源，非本次造成；該端點已隨
    2026-08-01 續段語音 WS 直送移除）。仍複製 context 是為了帶走 `log_trace`
    之類**未來**可能掛上的橫切狀態，成本為零；但不要在註解裡宣稱它修好了 span 巢狀。
    """
    if inbound_audio is None:
        return

    def upload_and_attach() -> None:
        try:
            url = inbound_audio.publish(audio, content_type="audio/m4a")
        except Exception:  # noqa: BLE001 - 上傳失敗不可中斷對話（已在背景執行）
            logger.warning("App 進站音檔上傳失敗")
            return
        if traces is not None:
            attach_source_audio_url(traces, trace_id, url)

    context = contextvars.copy_context()
    threading.Thread(
        target=lambda: context.run(upload_and_attach),
        name="kinsun-inbound-upload",
        daemon=True,
    ).start()
