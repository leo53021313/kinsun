"""安撫話音檔快取的守門測試（spec 2026-07-28 P2）。

核心契約只有兩條，但兩條都很硬：
1. **對話路徑上絕不合成、絕不上傳、絕不拋例外**——安撫話的全部價值就是「立刻」，
   讓它去擋長輩的回覆是本末倒置。
2. **取不到就回 None＝這輪不講**，是降級不是錯誤。
"""

from __future__ import annotations

import random
import threading

from kinsun.speech import acks
from kinsun.speech.ack_audio import AckAudioCache
from kinsun.speech.tts import (
    TTSError,
    TtsPriority,
    TtsResult,
    VoiceReference,
    current_tts_priority,
)


class _FakeTts:
    def __init__(self, *, fail_on: set[str] | None = None, audio: bytes | None = b"m4a") -> None:
        self.calls: list[str] = []
        self.priorities: list[TtsPriority] = []
        # 每次合成收到的 voice 參數（2026-08-19）：克隆批次必須以那個聲音合成。
        self.voices: list[VoiceReference | None] = []
        self._fail_on = fail_on or set()
        self._audio = audio

    def synthesize(self, text: str, *, voice=None) -> TtsResult:
        self.calls.append(text)
        self.priorities.append(current_tts_priority())
        self.voices.append(voice)
        if text in self._fail_on:
            raise TTSError("假的合成失敗")
        return TtsResult(text=text, audio=self._audio, duration_ms=len(text) * 100)


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.published: list[bytes] = []
        self._fail = fail
        self._n = 0

    def publish(self, audio: bytes, *, content_type: str) -> str:
        if self._fail:
            raise RuntimeError("假的上傳失敗")
        self.published.append(audio)
        self._n += 1
        return f"https://example.test/ack-{self._n}.m4a"


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _cache(tts=None, publisher=None, *, ttl=86400.0, clock=None, seed=0):
    return AckAudioCache(
        tts or _FakeTts(),
        publisher or _FakePublisher(),
        signed_url_ttl_seconds=ttl,
        clock=clock or _Clock(),
        rng=random.Random(seed),
    )


def _drain_background_threads():
    for thread in threading.enumerate():
        if thread.name.startswith("kinsun-ack") and thread is not threading.current_thread():
            thread.join(timeout=5)


# ── 預熱 ────────────────────────────────────────────────────────────────


def test_prewarm_synthesises_every_phrase_once():
    tts, publisher = _FakeTts(), _FakePublisher()
    cache = _cache(tts, publisher)
    cache.prewarm()
    assert sorted(tts.calls) == sorted(acks.all_phrases())
    assert len(publisher.published) == len(acks.all_phrases())
    assert cache.warm_count() == len(acks.all_phrases())


def test_prewarm_runs_at_the_lowest_priority():
    """沒有任何人在等預熱，它必須讓路給長輩正在等的回覆。"""
    tts = _FakeTts()
    _cache(tts).prewarm()
    assert set(tts.priorities) == {TtsPriority.PREWARM}


def test_one_failing_phrase_does_not_take_down_the_rest():
    """TTS 服務實測會偶發 400 與瞬斷；一句失敗不可讓其餘的都沒有音檔。"""
    broken = acks.all_phrases()[0]
    tts = _FakeTts(fail_on={broken})
    cache = _cache(tts)
    cache.prewarm()
    assert cache.warm_count() == len(acks.all_phrases()) - 1


def test_upload_failure_leaves_the_phrase_unavailable_but_does_not_raise():
    cache = _cache(publisher=_FakePublisher(fail=True))
    cache.prewarm()
    assert cache.warm_count() == 0


def test_text_bubble_backend_produces_no_clips():
    """本機開發用文字泡泡沒有音檔——安撫話只有語音才有意義，不該產生半套的項目。"""
    cache = _cache(_FakeTts(audio=None))
    cache.prewarm()
    assert cache.warm_count() == 0


# ── 對話路徑 ────────────────────────────────────────────────────────────


def test_clip_for_returns_a_warm_clip_without_touching_tts():
    """⭐ 最重要的一條：暖好之後，對話路徑上一次 TTS 都不能再打。"""
    tts, publisher = _FakeTts(), _FakePublisher()
    cache = _cache(tts, publisher)
    cache.prewarm()
    calls_after_prewarm = len(tts.calls)

    clip = cache.clip_for("get_news")
    assert clip is not None
    assert clip.text in acks.phrases_for("get_news")
    assert clip.audio_url.startswith("https://example.test/ack-")
    assert clip.duration_ms == len(clip.text) * 100
    assert len(tts.calls) == calls_after_prewarm, "對話路徑上不該再合成"
    assert len(publisher.published) == len(acks.all_phrases()), "對話路徑上不該再上傳"


def test_clip_for_returns_none_before_prewarm_and_self_heals():
    """還沒暖好就這輪不講，並在背景補上——下一輪就有了。"""
    tts = _FakeTts()
    cache = _cache(tts)
    assert cache.clip_for("get_news") is None
    _drain_background_threads()
    assert cache.warm_count() >= 1
    assert cache.clip_for("get_news") is not None


def test_clip_for_uses_the_tool_specific_pool():
    cache = _cache()
    cache.prewarm()
    for _ in range(10):
        assert cache.clip_for("get_route").text in acks.phrases_for("get_route")


def test_unknown_tool_falls_back_to_the_generic_pool():
    cache = _cache()
    cache.prewarm()
    clip = cache.clip_for("還沒做的工具")
    assert clip is not None
    assert clip.text in acks.persona().generic


def test_clip_for_never_raises_when_everything_is_broken():
    """安撫話是加分項：後端全壞也只能是「這輪不講」，不可讓整輪對話失敗。"""
    cache = _cache(_FakeTts(fail_on=set(acks.all_phrases())), _FakePublisher(fail=True))
    assert cache.clip_for("get_news") is None
    _drain_background_threads()
    assert cache.clip_for("get_news") is None


# ── 簽章過期與自癒 ──────────────────────────────────────────────────────


def test_expired_signature_is_treated_as_missing_and_refreshed():
    """`publish` 回的是短效簽章 URL，不是永久網址。過期的網址播不出聲音，
    所以必須當成沒有——那一輪不講，背景重新上傳。"""
    clock = _Clock()
    tts, publisher = _FakeTts(), _FakePublisher()
    cache = _cache(tts, publisher, ttl=3600.0, clock=clock)
    cache.prewarm()
    assert cache.clip_for("get_news") is not None

    clock.now += 3600.0  # 過期
    assert cache.clip_for("get_news") is None, "過期的網址不可拿來播"
    _drain_background_threads()
    assert cache.clip_for("get_news") is not None, "背景沒有補回來"


def test_margin_means_a_clip_expires_slightly_early():
    """留 10 分鐘餘裕，避免「取的時候還沒過期、長輩播的時候已經過期」。"""
    clock = _Clock()
    cache = _cache(ttl=3600.0, clock=clock)
    cache.prewarm()
    clock.now += 3000.0  # 距到期 600 秒＝正好踩到餘裕
    assert cache.clip_for("get_news") is None


def test_concurrent_misses_only_refresh_a_phrase_once():
    """長輩連續發話時不該把同一段重複合成好幾次。"""
    tts = _FakeTts()
    cache = _cache(tts, seed=1)
    phrase = acks.phrases_for("get_weather")[0]

    threads = [
        threading.Thread(target=lambda: cache.clip_for("get_weather"), daemon=True)
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    _drain_background_threads()
    assert tts.calls.count(phrase) == 1, f"同一句被合成了 {tts.calls.count(phrase)} 次"


# ── 待命話術（V-02，2026-07-29）──────────────────────────────────────────
#
# 回退話術「金孫這邊有點小狀況…」也必須有音檔：管線失敗時走的是它，而看不到螢幕的
# 長輩只有聲音這一條路。它不屬於工具安撫話語庫（那裡的句子語意是「正在查」），
# 故以 standby_phrases 從組裝根注入，快取本身不需要知道那句話為什麼重要。


def test_standby_phrases_are_prewarmed_alongside_the_ack_library():
    tts = _FakeTts()
    cache = AckAudioCache(
        tts,
        _FakePublisher(),
        signed_url_ttl_seconds=86400.0,
        clock=_Clock(),
        standby_phrases=("金孫這邊有點小狀況",),
    )
    cache.prewarm()
    assert "金孫這邊有點小狀況" in tts.calls


# ── 長輩客製化聲音（Leo 2026-08-19 需求）─────────────────────────────────
#
# 家屬設了克隆聲音的長輩，過場語也要是那個聲音——回答是孫子的聲音、過場卻是預設
# 聲音，等於同一輪對話講到一半換人。快取因此分批：預設聲音一批、每個 elder_id＋版本
# 各一批。


def _grandson_voice(version: str = "1000.0") -> VoiceReference:
    return VoiceReference(
        elder_id="e1",
        prompt_audio_url=f"https://signed.test/voice-refs/e1?v={version}",
        prompt_text="阿嬤我是小明",
        version=version,
    )


def test_cloned_voice_batch_synthesises_with_that_voice():
    """克隆批次的每一句都必須帶著那個聲音去合成，暖好之後查表即回。"""
    tts = _FakeTts()
    cache = _cache(tts)
    voice = _grandson_voice()
    assert cache.clip_for("get_news", voice=voice) is None, "還沒暖好＝這輪不講"
    _drain_background_threads()

    clip = cache.clip_for("get_news", voice=voice)
    assert clip is not None
    assert clip.text in acks.phrases_for("get_news")
    cloned = [v for v in tts.voices if v is not None]
    assert cloned, "克隆批次沒有任何一句以克隆聲音合成"
    assert all(v == voice for v in cloned)


def test_cloned_voice_never_falls_back_to_the_default_batch():
    """⭐ 需求明定過場不可以是預設聲音：克隆批次還沒暖好時寧可安靜，
    也不能在同一輪裡「過場預設聲、回答克隆聲」講到一半換人。"""
    cache = _cache()
    cache.prewarm()  # 預設聲音批次已暖
    assert cache.clip_for("get_news", voice=_grandson_voice()) is None


def test_default_voice_elders_are_unaffected_by_cloned_batches():
    """沒有克隆聲音的長輩照舊吃預設批次，不受任何克隆批次影響。"""
    cache = _cache()
    cache.prewarm()
    _ = cache.clip_for("get_news", voice=_grandson_voice())  # 觸發克隆批次背景暖
    _drain_background_threads()
    clip = cache.clip_for("get_news")
    assert clip is not None


def test_re_recording_drops_the_old_cloned_batch():
    """家屬重錄＝版本換值＝新批次；開始暖新批次時舊版本批次整批丟掉，
    舊克隆聲音從此無從被取用（需求明定不可以再聽到舊克隆聲音）。"""
    tts = _FakeTts()
    cache = _cache(tts)
    old, new = _grandson_voice("1000.0"), _grandson_voice("2000.0")

    cache.clip_for("get_news", voice=old)
    _drain_background_threads()
    assert cache.clip_for("get_news", voice=old) is not None
    count_with_old = cache.warm_count()

    cache.clip_for("get_news", voice=new)  # 重錄後第一次：暖新批次、丟舊批次
    _drain_background_threads()
    assert cache.clip_for("get_news", voice=new) is not None
    assert cache.warm_count() == count_with_old, "舊版本批次沒被丟掉（總句數應持平：舊換新）"


def test_ensure_warm_prewarms_a_cloned_voice_before_the_first_tool_call():
    """輪次開頭就先暖：整批預錄要半分鐘，等第一次工具呼叫才開始就全趕不上。"""
    cache = _cache()
    voice = _grandson_voice()
    cache.ensure_warm(voice)
    _drain_background_threads()
    assert cache.clip_for("get_news", voice=voice) is not None


def test_ensure_warm_without_a_cloned_voice_is_a_no_op():
    """預設聲音批次由啟動時的 start_prewarm 負責，ensure_warm(None) 不該多做事。"""
    tts = _FakeTts()
    cache = _cache(tts)
    cache.prewarm()  # 預設批次照常由啟動預熱備妥
    calls_after_prewarm = len(tts.calls)

    cache.ensure_warm(None)
    _drain_background_threads()

    assert len(tts.calls) == calls_after_prewarm, "ensure_warm(None) 不該多合成任何一句"
    assert cache.warm_count() == len(acks.all_phrases()), "批次數量不該因 ensure_warm(None) 改變"


def test_clip_for_text_returns_that_exact_phrase():
    cache = AckAudioCache(
        _FakeTts(),
        _FakePublisher(),
        signed_url_ttl_seconds=86400.0,
        clock=_Clock(),
        standby_phrases=("金孫這邊有點小狀況",),
    )
    cache.prewarm()
    clip = cache.clip_for_text("金孫這邊有點小狀況")
    assert clip is not None
    assert clip.text == "金孫這邊有點小狀況"
    assert clip.audio_url.startswith("https://example.test/ack-")
    assert clip.duration_ms > 0


def test_clip_for_text_returns_none_before_prewarm():
    """還沒暖好＝這輪沒有音檔可用，回 None 讓呼叫端退回文字——不是錯誤。"""
    cache = _cache()
    assert cache.clip_for_text("金孫這邊有點小狀況") is None


def test_clip_for_text_never_synthesises_on_the_calling_thread():
    """對話路徑的鐵律：合成要 1.9 秒，絕不可發生在長輩正在等的那條執行緒上。

    查不到會觸發背景整批重暖（既有自癒設計，`clip_for` 同款），所以斷言的不是
    「完全沒有合成」，而是「**呼叫端這條執行緒**沒有合成」——後者才是延遲的來源。
    """
    caller = threading.current_thread()
    threads: list[threading.Thread] = []

    class _ThreadRecordingTts(_FakeTts):
        def synthesize(self, text: str, *, voice=None) -> TtsResult:
            threads.append(threading.current_thread())
            return super().synthesize(text, voice=voice)

    cache = AckAudioCache(
        _ThreadRecordingTts(), _FakePublisher(), signed_url_ttl_seconds=86400.0, clock=_Clock()
    )
    assert cache.clip_for_text("沒暖過的句子") is None
    _drain_background_threads()
    assert threads, "背景自癒應該有跑，否則這個測試沒有在驗任何事"
    assert caller not in threads


def test_expired_standby_clip_is_treated_as_missing():
    """簽章過期的音檔播不出來，等同沒有——寧可退回文字，不可送出播不出的網址。"""
    clock = _Clock()
    cache = AckAudioCache(
        _FakeTts(),
        _FakePublisher(),
        signed_url_ttl_seconds=86400.0,
        clock=clock,
        standby_phrases=("金孫這邊有點小狀況",),
    )
    cache.prewarm()
    assert cache.clip_for_text("金孫這邊有點小狀況") is not None
    clock.now += 86400.0
    assert cache.clip_for_text("金孫這邊有點小狀況") is None
    _drain_background_threads()
