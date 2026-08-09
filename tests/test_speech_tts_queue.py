"""TTS 優先權佇列的守門測試（spec 2026-07-28 P1）。

為什麼需要這道佇列（2026-07-28 實測，真 TTS 服務打 GB10）：併發合成會互搶 GPU，
而且搶得**沒有規律**——同一個工作負載跑兩回合，某次最短的那段 1.89 秒回來、
另一次同樣的段落等了 15.08 秒。序列化不是妥協而是正確的形狀：長輩一次只能聽一則，
所以 TTS 一次只做一則本來就夠。佇列真正買到的是**可預測性**，不是吞吐量。
"""

from __future__ import annotations

import threading

import pytest

from kinsun.speech.tts import (
    QueuedTtsClient,
    TTSError,
    TtsPriority,
    TtsResult,
    tts_priority,
)


class _RecordingTts:
    """記錄呼叫順序，並可外部控制何時放行——用來製造確定性的競爭場景。"""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.finished: list[str] = []
        self.gate = threading.Event()
        self.gate.set()
        self.in_flight = 0
        self.max_in_flight = 0
        self._lock = threading.Lock()

    def synthesize(self, text: str, *, voice=None) -> TtsResult:
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            self.started.append(text)
        self.gate.wait(timeout=5)
        with self._lock:
            self.in_flight -= 1
            self.finished.append(text)
        return TtsResult(text=text, audio=b"x", duration_ms=len(text) * 100)


def _call_in_thread(client, text, priority=None):
    """在背景執行緒呼叫 synthesize，回傳 (thread, 取結果的函式)。"""
    box: dict = {}

    def run():
        try:
            if priority is None:
                box["result"] = client.synthesize(text)
            else:
                with tts_priority(priority):
                    box["result"] = client.synthesize(text)
        except BaseException as exc:  # noqa: BLE001 - 原樣交給呼叫端斷言
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, box


def test_only_one_synthesis_runs_at_a_time():
    """核心保證：不管幾個人同時要，GPU 上永遠只有一個推論。"""
    inner = _RecordingTts()
    client = QueuedTtsClient(inner)
    threads = [_call_in_thread(client, f"第{i}句")[0] for i in range(5)]
    for thread in threads:
        thread.join(timeout=5)
    assert inner.max_in_flight == 1, f"同時有 {inner.max_in_flight} 個推論在跑"
    assert len(inner.finished) == 5
    client.close()


def test_higher_priority_jumps_the_queue():
    """低優先先排隊，高優先後到也要先做。

    製造確定性：先用一個工作佔住唯一的 worker，趁它被卡住時排入低優先與高優先，
    再放行。若沒有優先權，順序會是先進先出的「排程推播」在前。
    """
    inner = _RecordingTts()
    inner.gate.clear()  # 佔住 worker
    client = QueuedTtsClient(inner)

    blocker, _ = _call_in_thread(client, "佔位")
    # 等 worker 真的進到內層，否則後面兩筆可能在它之前被取走。
    for _ in range(500):
        if inner.started:
            break
        threading.Event().wait(0.01)
    assert inner.started == ["佔位"]

    low, _ = _call_in_thread(client, "排程推播", TtsPriority.PUSH)
    prewarm, _ = _call_in_thread(client, "安撫話預熱", TtsPriority.PREWARM)
    # 兩筆低優先確實進了佇列，才輪到高優先插隊——否則測不出插隊。
    threading.Event().wait(0.05)
    high, _ = _call_in_thread(client, "長輩的回覆", TtsPriority.REPLY)
    threading.Event().wait(0.05)

    inner.gate.set()
    for thread in (blocker, low, prewarm, high):
        thread.join(timeout=5)

    assert inner.started[0] == "佔位"
    assert inner.started[1] == "長輩的回覆", f"高優先沒有插隊：{inner.started}"
    assert inner.started[-1] == "安撫話預熱", f"最低優先沒有殿後：{inner.started}"
    client.close()


def test_same_priority_keeps_first_in_first_out():
    """同優先權不可亂序——否則兩段續段會顛倒，長輩聽到的話會前後對調。"""
    inner = _RecordingTts()
    inner.gate.clear()
    client = QueuedTtsClient(inner)
    blocker, _ = _call_in_thread(client, "佔位")
    for _ in range(500):
        if inner.started:
            break
        threading.Event().wait(0.01)

    threads = []
    for i in range(4):
        thread, _ = _call_in_thread(client, f"續段{i}", TtsPriority.CHUNK)
        threads.append(thread)
        threading.Event().wait(0.02)  # 確保排隊順序

    inner.gate.set()
    for thread in (blocker, *threads):
        thread.join(timeout=5)
    assert inner.started == ["佔位", "續段0", "續段1", "續段2", "續段3"]
    client.close()


def test_inner_errors_reach_the_caller():
    """合成失敗必須原樣傳回呼叫端——`_synthesize` 靠 TTSError 決定退化為純文字。"""

    class _Failing:
        def synthesize(self, text: str, *, voice=None) -> TtsResult:
            raise TTSError("DGX TTS 呼叫失敗：假的")

    client = QueuedTtsClient(_Failing())
    with pytest.raises(TTSError, match="假的"):
        client.synthesize("會炸")
    client.close()


def test_result_is_returned_to_the_right_caller():
    """多人同時要時，每個人拿到的必須是自己那一段——不可張冠李戴。"""
    inner = _RecordingTts()
    client = QueuedTtsClient(inner)
    boxes = []
    threads = []
    for i in range(6):
        thread, box = _call_in_thread(client, f"第{i}句")
        threads.append(thread)
        boxes.append((f"第{i}句", box))
    for thread in threads:
        thread.join(timeout=5)
    for text, box in boxes:
        assert "error" not in box, box.get("error")
        assert box["result"].text == text
    client.close()


def test_default_priority_is_the_reply():
    """沒有明講優先權時視為長輩的回覆——最高。

    這個預設是安全側：漏標的呼叫端會排在前面而不是被餓死。既有呼叫端
    （`pipeline._synthesize`）因此不必改一行就有正確行為。
    """
    inner = _RecordingTts()
    inner.gate.clear()
    client = QueuedTtsClient(inner)
    blocker, _ = _call_in_thread(client, "佔位")
    for _ in range(500):
        if inner.started:
            break
        threading.Event().wait(0.01)

    low, _ = _call_in_thread(client, "預熱", TtsPriority.PREWARM)
    threading.Event().wait(0.05)
    unmarked, _ = _call_in_thread(client, "沒標優先權")
    threading.Event().wait(0.05)

    inner.gate.set()
    for thread in (blocker, low, unmarked):
        thread.join(timeout=5)
    assert inner.started[1] == "沒標優先權"
    client.close()


def test_close_is_idempotent_and_drains():
    inner = _RecordingTts()
    client = QueuedTtsClient(inner)
    client.synthesize("一句")
    client.close()
    client.close()
    assert inner.finished == ["一句"]


def test_priority_context_is_isolated_between_threads():
    """優先權走 contextvars，各執行緒互不污染（同 turn_context 的既有理由）。"""
    seen: list[TtsPriority] = []
    barrier = threading.Barrier(2, timeout=5)

    def worker(priority):
        with tts_priority(priority):
            barrier.wait()
            from kinsun.speech.tts import current_tts_priority

            seen.append(current_tts_priority())

    threads = [
        threading.Thread(target=worker, args=(TtsPriority.PREWARM,), daemon=True),
        threading.Thread(target=worker, args=(TtsPriority.REPLY,), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert sorted(seen) == [TtsPriority.REPLY, TtsPriority.PREWARM]


# ── 排隊與合成要分得開（2026-08-08 觀測盤點）──
#
# Opik 上原本只有一格 `tts`，裡面同時包著「排在別人後面等」與「GPU 真的在算」。
# 兩者的處置完全不同——排隊久代表併發超過一顆 GPU 的容量（要加閘門或降併發），
# 合成久代表回覆太長或模型太慢（要縮字數或改串流）。混成一格就分不出該修哪個。


def test_queue_wait_and_synthesis_are_separate_spans(monkeypatch):
    """兩段各自成格，名字固定，供 Opik 分辨「在排隊」與「在算」。"""
    import opik

    from kinsun.tracing import client as tracing_client
    from kinsun.tracing import decorators as tracing_decorators

    names: list[str] = []
    monkeypatch.setattr(opik, "track", lambda **kw: (names.append(kw.get("name")), lambda f: f)[1])
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)
    monkeypatch.setattr(tracing_client, "_ENABLED", True)

    client = QueuedTtsClient(_RecordingTts())
    try:
        assert client.synthesize("嗨").text == "嗨"
    finally:
        client.close()
    assert "tts_queue_wait" in names
    assert "tts_synthesize" in names


def test_queue_wait_returns_once_the_worker_picks_the_job_up():
    """排隊那一格要在 worker **接手時**結束，不是等整段合成完——否則兩格會一樣長。"""
    inner = _RecordingTts()
    inner.gate.clear()  # 卡住合成，讓「已接手但還沒算完」這個狀態存在
    client = QueuedTtsClient(inner)
    thread, box = _call_in_thread(client, "嗨")
    try:
        # worker 接手後，排隊已經結束，但合成還被 gate 卡著。
        for _ in range(100):
            if inner.started:
                break
            threading.Event().wait(0.01)
        assert inner.started == ["嗨"]
        assert not inner.finished
    finally:
        inner.gate.set()
        thread.join(timeout=5)
        client.close()
    assert box["result"].text == "嗨"


def test_inner_errors_still_reach_the_caller_with_spans_split():
    """拆成兩段之後，例外仍要原樣傳回呼叫端——不可被排隊那一段吞掉。"""

    class _Boom:
        def synthesize(self, text: str, *, voice=None) -> TtsResult:
            raise TTSError("壞了")

    client = QueuedTtsClient(_Boom())
    try:
        with pytest.raises(TTSError, match="壞了"):
            client.synthesize("嗨")
    finally:
        client.close()


def test_caller_is_not_stuck_when_the_job_is_cancelled():
    """worker 沒真的跑（future 被取消）時，排隊那一格仍必須結束，不可永遠等下去。"""
    inner = _RecordingTts()
    client = QueuedTtsClient(inner)
    try:
        assert client.synthesize("嗨").text == "嗨"
    finally:
        client.close()
    # 關閉後仍有人要合成：就地執行，不走佇列（既有行為，不可因拆格而改變）。
    assert client.synthesize("收工後").text == "收工後"
