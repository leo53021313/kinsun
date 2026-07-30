"""進站音檔背景上傳的離線測試（2026-07-30 延遲優化 B1＋審查 H1）。

重心是**補寫的競態**：`record_asr_call`（INSERT）與這裡的 UPDATE 之間沒有順序保證，
上傳較快時 UPDATE 會打在還不存在的列上。這條路的失敗形態極度隱蔽——檔案已經上傳
成功、佔著 Storage 配額，但沒有任何指標指向它，而它正是兩次 ASR 根因診斷唯一的原始
證據來源。故重試與「重試用盡留 warning」兩件事都要有測試守。
"""

from __future__ import annotations

from kinsun.channels.app.inbound_audio import attach_source_audio_url, start_inbound_upload


class _RecordingTraces:
    """依 `hits` 腳本決定第幾次呼叫才打中那一列。"""

    def __init__(self, hits: list[bool]) -> None:
        self._hits = list(hits)
        self.calls: list[tuple[str, str]] = []

    def update_asr_source_audio_url(self, *, trace_id: str, source_audio_url: str) -> bool:
        self.calls.append((trace_id, source_audio_url))
        return self._hits.pop(0) if self._hits else False


def _no_sleep(_seconds: float) -> None:
    pass


def test_attach_succeeds_on_the_first_try_without_sleeping():
    traces = _RecordingTraces([True])
    slept: list[float] = []

    assert attach_source_audio_url(
        traces, "t1", "https://x/in.m4a", sleep=slept.append, delays=(0.0, 1.0, 2.0)
    )
    assert traces.calls == [("t1", "https://x/in.m4a")]
    assert slept == []  # 常見情形（ASR 已經落庫）不可付任何等待成本


def test_attach_retries_until_the_asr_row_shows_up():
    """上傳比 ASR 快：前兩次 0 列更新，第三次才打中——這是常態而非邊緣情形。"""
    traces = _RecordingTraces([False, False, True])

    assert attach_source_audio_url(
        traces, "t2", "https://x/in.m4a", sleep=_no_sleep, delays=(0.0, 1.0, 2.0, 4.0)
    )
    assert len(traces.calls) == 3


def test_attach_warns_when_the_row_never_shows_up(caplog):
    """重試用盡＝這筆稽核斷了。**必須**留一行看得見的 warning，不可靜默。"""
    traces = _RecordingTraces([False, False])

    with caplog.at_level("WARNING", logger="kinsun.channels.app"):
        assert not attach_source_audio_url(
            traces, "t3", "https://x/in.m4a", sleep=_no_sleep, delays=(0.0, 1.0)
        )
    assert "無處可掛" in caplog.text
    assert "t3" in caplog.text  # 沒有 trace_id 的 warning 事後查不到是哪一輪


class _BoomTraces:
    def update_asr_source_audio_url(self, *, trace_id: str, source_audio_url: str) -> bool:
        raise RuntimeError("boom")


def test_attach_swallows_store_errors_without_retrying():
    """觀測補寫爆炸不可影響任何人；也不該對一個會爆的 store 重試四次。"""
    assert not attach_source_audio_url(
        _BoomTraces(), "t4", "https://x/in.m4a", sleep=_no_sleep, delays=(0.0, 1.0)
    )


class _StubPublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.published: list[bytes] = []

    def publish(self, audio: bytes, *, content_type: str) -> str:
        if self._fail:
            raise RuntimeError("上傳掛了")
        self.published.append(audio)
        return "https://x/uploaded.m4a"


def _join_upload_threads() -> None:
    """等背景上傳執行緒收工（daemon，測試裡要等它才看得到結果）。"""
    import threading

    for thread in threading.enumerate():
        if thread.name == "kinsun-inbound-upload":
            thread.join(timeout=5)


def test_start_inbound_upload_publishes_and_attaches_in_the_background():
    publisher = _StubPublisher()
    traces = _RecordingTraces([True])

    start_inbound_upload(publisher, traces, b"\x00\x01", "t5")
    _join_upload_threads()

    assert publisher.published == [b"\x00\x01"]
    assert traces.calls == [("t5", "https://x/uploaded.m4a")]


def test_upload_failure_leaves_the_row_untouched():
    """上傳失敗＝那一列的 `source_audio_url` 維持空字串，與「未設定音檔託管」同一種降級。"""
    traces = _RecordingTraces([True])

    start_inbound_upload(_StubPublisher(fail=True), traces, b"\x00", "t6")
    _join_upload_threads()

    assert traces.calls == []


def test_no_publisher_configured_is_a_noop():
    traces = _RecordingTraces([True])
    start_inbound_upload(None, traces, b"\x00", "t7")
    _join_upload_threads()
    assert traces.calls == []


def test_no_traces_configured_still_uploads():
    """觀測未接線時仍要留檔（音檔本身有價值），只是沒有地方掛網址。"""
    publisher = _StubPublisher()
    start_inbound_upload(publisher, None, b"\x00", "t8")
    _join_upload_threads()
    assert publisher.published == [b"\x00"]
