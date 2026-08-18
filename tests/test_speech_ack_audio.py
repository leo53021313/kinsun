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
        self.voices: list[object] = []
        self.priorities: list[TtsPriority] = []
        self._fail_on = fail_on or set()
        self._audio = audio

    def synthesize(self, text: str, *, voice=None) -> TtsResult:
        self.calls.append(text)
        self.voices.append(voice)
        self.priorities.append(current_tts_priority())
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


def _cache(tts=None, publisher=None, *, ttl=86400.0, clock=None, seed=0, resolve_voice=None):
    return AckAudioCache(
        tts or _FakeTts(),
        publisher or _FakePublisher(),
        signed_url_ttl_seconds=ttl,
        clock=clock or _Clock(),
        rng=random.Random(seed),
        resolve_voice=resolve_voice,
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
    assert cache.warm_count() == len(acks.all_phrases()) + 1


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


# ── 逐長輩的專屬聲音（2026-08-18）────────────────────────────────────────
#
# 起因是實機回報：長輩在同一輪裡先聽到預設聲音的「我幫你查查」、再聽到家屬聲音的
# 答案，像換了個人在講話。安撫話原本只有一份、以全域聲音合成——那在「全系統一個
# 聲音」的年代與回覆一致，客製化聲音上線後前提就失效了。


def _voice(elder_id="e1"):
    return VoiceReference(
        elder_id=elder_id,
        prompt_audio_url="https://example.test/ref.wav",
        prompt_text="阿嬤您好",
        version="1",
    )


def test_an_elder_with_a_custom_voice_gets_acks_in_that_voice():
    """安撫話要跟回覆同一個聲音——這正是本次要修掉的症狀。"""
    tts = _FakeTts()
    cache = _cache(tts, resolve_voice=lambda eid: _voice(eid))

    cache.prewarm("e1")

    assert cache.warm_count("e1") > 0
    assert tts.voices, "應該有合成過"
    assert all(v is not None and v.elder_id == "e1" for v in tts.voices), (
        "每一句都要用該長輩的參考語音合成"
    )


def test_a_not_yet_warm_elder_gets_no_ack_rather_than_the_default_voice():
    """⚠️ 這條是本次修正的核心取捨，改壞了不會有任何測試以外的地方報錯。

    有專屬聲音的長輩，安撫話沒暖好時**寧可不講**也不要用全域預設聲音頂替——
    頂替就是「同一輪裡換一個人講話」，正是我們要修掉的東西。乾等是既有的體感，
    換聲音是新的缺陷，兩者嚴重度不同。
    """
    cache = _cache(resolve_voice=lambda eid: _voice(eid))
    cache.prewarm()  # 只暖全域那一批

    assert cache.warm_count() > 0, "全域那批有暖好"
    assert cache.clip_for("news", elder_id="e1") is None, "不可以拿全域預設聲音頂替"
    _drain_background_threads()


def test_an_elder_without_a_custom_voice_still_gets_the_default_acks():
    """絕大多數長輩沒有專屬聲音，他們的安撫話不可以因為這次改動而消失。"""
    cache = _cache(resolve_voice=lambda eid: None)
    cache.prewarm()

    clip = cache.clip_for("news", elder_id="e-no-profile")

    assert clip is not None and clip.audio_url


def test_revoking_drops_only_that_elders_acks():
    """撤銷後回到全域預設聲音，且不可波及其他長輩。"""
    cache = _cache(resolve_voice=lambda eid: _voice(eid))
    cache.prewarm()
    cache.prewarm("e1")
    cache.prewarm("e2")

    cache.drop_elder("e1")

    assert cache.warm_count("e1") == 0
    assert cache.warm_count("e2") > 0, "別人的不可以被連坐"
    assert cache.warm_count() > 0, "全域那批也不可以被清掉"


def test_one_elders_expiry_does_not_wipe_everyone_else():
    """各桶是各自整批上傳的，效期互不相干。

    連坐的話其他長輩會平白少掉好幾輪安撫話——而那是靜默的，沒有人會發現。
    """
    clock = _Clock()
    cache = _cache(clock=clock, ttl=100.0, resolve_voice=lambda eid: _voice(eid))
    cache.prewarm("e1")
    clock.now += 90.0  # 只有 e1 這批接近到期
    cache.prewarm("e2")

    assert cache.clip_for("news", elder_id="e1") is None, "過期的那批要被清掉"
    assert cache.warm_count("e2") > 0, "剛暖好的那批不受影響"
    _drain_background_threads()


def test_a_broken_voice_lookup_never_breaks_the_turn():
    """查設定檔失敗＝當成沒有專屬聲音。安撫話是加分項，不可以讓整輪對話出事。"""

    def boom(elder_id):
        raise RuntimeError("資料庫掛了")

    cache = _cache(resolve_voice=boom)
    cache.prewarm()

    clip = cache.clip_for("news", elder_id="e1")

    assert clip is not None, "退回全域預設聲音，而不是拋例外"
