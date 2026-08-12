"""DGX TTS 服務的離線測試（✅ 庚-24／A-13）：金鑰、請求驗證、併發閘、回應契約。

模型推論需 GPU＋CosyVoice repo，但這些純邏輯不需要——以 monkeypatch 換掉
`_synthesize`，在無 GPU 的 CI 上鎖住服務層行為與回應契約
（audio/mp4＋X-Duration-Ms，對應 kinsun.speech.tts.DgxTtsClient）。
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from services.tts import server as tts_server


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        tts_server, "_synthesize", lambda text, prompt_wav, prompt_text: (b"fake-m4a", 1234)
    )
    return TestClient(tts_server.app)


def test_healthz_reports_model_not_loaded(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "model_loaded": False, "stuck_workers": 0}


def test_synthesize_contract_media_type_and_duration_header(client):
    res = client.post("/synthesize", json={"text": "阿公早安"})
    assert res.status_code == 200
    assert res.content == b"fake-m4a"
    assert res.headers["content-type"] == "audio/mp4"
    assert res.headers["X-Duration-Ms"] == "1234"


def test_synthesize_requires_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(tts_server, "TTS_API_KEY", "sekret")
    no_key = client.post("/synthesize", json={"text": "哈囉"})
    ok = client.post("/synthesize", json={"text": "哈囉"}, headers={"X-Api-Key": "sekret"})
    assert no_key.status_code == 401
    assert ok.status_code == 200


def test_synthesize_rejects_missing_or_blank_text(client):
    assert client.post("/synthesize", json={}).status_code == 400
    res = client.post("/synthesize", json={"text": "  "})
    assert res.status_code == 400
    assert res.json()["detail"] == "missing_text"


def test_synthesize_rejects_overlong_text(client, monkeypatch):
    monkeypatch.setattr(tts_server, "TTS_MAX_TEXT_CHARS", 5)
    res = client.post("/synthesize", json={"text": "六個字的長句子"})
    assert res.status_code == 413
    assert res.json()["detail"] == "text_too_long"


def test_synthesize_sheds_load_when_queue_full(client, monkeypatch):
    monkeypatch.setattr(
        tts_server, "_inflight", tts_server.TTS_MAX_CONCURRENCY + tts_server.TTS_MAX_QUEUE
    )
    res = client.post("/synthesize", json={"text": "哈囉"})
    assert res.status_code == 503
    assert res.json()["detail"] == "overloaded"


def test_synthesize_passes_elder_voice_fields_through(client, monkeypatch):
    """長輩客製化聲音複製（2026-07-30）：/synthesize 收到 elder_id 等欄位時，
    會轉交給 _resolve_voice 解析出實際要用的參考音檔／逐字稿。"""
    calls = []

    def fake_resolve_voice(elder_id, prompt_audio_url, prompt_text, prompt_version):
        calls.append((elder_id, prompt_audio_url, prompt_text, prompt_version))
        return "/cached/e1.wav", "客製逐字稿"

    monkeypatch.setattr(tts_server, "_resolve_voice", fake_resolve_voice)
    res = client.post(
        "/synthesize",
        json={
            "text": "哈囉",
            "elder_id": "e1",
            "prompt_audio_url": "https://example.test/e1.wav",
            "prompt_text": "客製逐字稿",
            "prompt_version": "1000.0",
        },
    )
    assert res.status_code == 200
    # 版本一併轉交（2026-08-12）：漏掉它，家屬重錄之後這裡照樣命中舊快取。
    assert calls == [("e1", "https://example.test/e1.wav", "客製逐字稿", "1000.0")]


def test_synthesize_without_prompt_version_stays_backward_compatible(client, monkeypatch):
    """舊呼叫端不帶 prompt_version 時當空字串，行為與加入本欄位前相同。"""
    calls = []

    def fake_resolve_voice(elder_id, prompt_audio_url, prompt_text, prompt_version):
        calls.append(prompt_version)
        return "/cached/e1.wav", "客製逐字稿"

    monkeypatch.setattr(tts_server, "_resolve_voice", fake_resolve_voice)
    res = client.post("/synthesize", json={"text": "哈囉", "elder_id": "e1"})
    assert res.status_code == 200
    assert calls == [""]


class _FakeHttpResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_resolve_voice_without_elder_id_returns_global_default(monkeypatch):
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")
    assert tts_server._resolve_voice("", "", "") == ("/default.wav", "預設逐字稿")


def test_resolve_voice_falls_back_when_no_cache_and_no_url(monkeypatch):
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")
    assert tts_server._resolve_voice("e1", "", "") == ("/default.wav", "預設逐字稿")


def test_resolve_voice_downloads_once_then_reuses_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        return _FakeHttpResponse(b"WAVDATA")

        # 轉檔以替身代替：本測試的對象是下載與快取邏輯，不是 ffmpeg

    # （單元測試環境沒有 ffmpeg，真正的正規化另有專門的測試）。
    monkeypatch.setattr(
        tts_server, "_normalize_to_wav", lambda audio, dest: pathlib.Path(dest).write_bytes(audio)
    )
    monkeypatch.setattr(tts_server.urllib.request, "urlopen", fake_urlopen)

    wav_path, text = tts_server._resolve_voice("e1", "https://example.test/v.wav", "逐字稿")
    assert text == "逐字稿"
    assert (tmp_path / "voice-e1.wav").read_bytes() == b"WAVDATA"
    assert len(calls) == 1

    # 第二次同一個 elder_id：命中快取，不重新下載（即便沒再帶 prompt_audio_url）。
    wav_path2, text2 = tts_server._resolve_voice("e1", "", "")
    assert wav_path2 == wav_path
    assert text2 == "逐字稿"
    assert len(calls) == 1


def test_resolve_voice_cache_evicts_oldest_when_full(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_SIZE", 1)
    # 轉檔以替身代替：本測試的對象是下載與快取邏輯，不是 ffmpeg
    # （單元測試環境沒有 ffmpeg，真正的正規化另有專門的測試）。
    monkeypatch.setattr(
        tts_server, "_normalize_to_wav", lambda audio, dest: pathlib.Path(dest).write_bytes(audio)
    )
    monkeypatch.setattr(
        tts_server.urllib.request, "urlopen", lambda url, timeout=None: _FakeHttpResponse(b"W")
    )

    tts_server._resolve_voice("e1", "https://example.test/e1.wav", "e1 逐字稿")
    tts_server._resolve_voice("e2", "https://example.test/e2.wav", "e2 逐字稿")
    assert "e1" not in tts_server._voice_cache
    assert "e2" in tts_server._voice_cache


def test_resolve_voice_redownloads_when_the_family_re_records(monkeypatch, tmp_path):
    """家屬重錄後必須換成新錄音（2026-08-12）。

    ⚠️ 這是本檔最容易寫錯的一條，錯法是只斷言「有回傳路徑」。快取原本只認 elder_id，
    命中就直接回傳、看都不看新的 `prompt_audio_url`——於是家屬重錄、`PUT` 覆蓋了
    bucket 同一個物件路徑，應用層也換發了簽章網址，DGX 端卻仍然拿舊檔案合成。
    症狀是「重錄完全沒有變化、也沒有任何錯誤訊息」，家屬只會以為自己操作錯了，
    而唯一的復原方式是等 20 位長輩把它擠出快取、或重啟整個 TTS 服務。

    版本取自 `voice_profiles.granted_at`（每次 `save` 都會換一個值），所以
    「重錄過」與「沒重錄」在這一層是分得出來的。
    """
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    downloads = []

    def fake_urlopen(url, timeout=None):
        downloads.append(url)
        return _FakeHttpResponse(b"NEW" if "v2" in url else b"OLD")

    monkeypatch.setattr(
        tts_server, "_normalize_to_wav", lambda audio, dest: pathlib.Path(dest).write_bytes(audio)
    )
    monkeypatch.setattr(tts_server.urllib.request, "urlopen", fake_urlopen)

    tts_server._resolve_voice("e1", "https://example.test/v1.wav", "逐字稿", "1000.0")
    assert (tmp_path / "voice-e1.wav").read_bytes() == b"OLD"
    assert len(downloads) == 1

    # 家屬重錄：granted_at 換了值，即便物件路徑相同也必須重新抓。
    wav_path, text = tts_server._resolve_voice(
        "e1", "https://example.test/v2.wav", "逐字稿", "2000.0"
    )
    assert len(downloads) == 2, "版本換了卻沒重新下載＝家屬重錄不生效"
    assert pathlib.Path(wav_path).read_bytes() == b"NEW"
    assert text == "逐字稿"

    # 版本沒變就不該重抓——重錄是少見動作，不可為它讓每一輪都多付一次下載。
    tts_server._resolve_voice("e1", "https://example.test/v2.wav", "逐字稿", "2000.0")
    assert len(downloads) == 2


def test_resolve_voice_evicting_the_cache_also_removes_the_local_file(monkeypatch, tmp_path):
    """淘汰快取時一併刪掉本機檔案（2026-08-12）。

    這些是長輩家人的聲音樣本，不是可以無限期堆在暫存目錄的中介檔；而且淘汰後
    那個檔案再也不會被讀到，留著只是佔磁碟與擴大外洩面。
    """
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_SIZE", 1)
    monkeypatch.setattr(
        tts_server, "_normalize_to_wav", lambda audio, dest: pathlib.Path(dest).write_bytes(audio)
    )
    monkeypatch.setattr(
        tts_server.urllib.request, "urlopen", lambda url, timeout=None: _FakeHttpResponse(b"W")
    )

    tts_server._resolve_voice("e1", "https://example.test/e1.wav", "e1 逐字稿", "1")
    assert (tmp_path / "voice-e1.wav").exists()
    tts_server._resolve_voice("e2", "https://example.test/e2.wav", "e2 逐字稿", "1")
    assert not (tmp_path / "voice-e1.wav").exists(), "被淘汰的聲音樣本不該留在磁碟上"


def test_resolve_voice_rejects_an_elder_id_that_is_not_a_plain_identifier(monkeypatch, tmp_path):
    """`elder_id` 直接參與檔案路徑，格式不合就退回全域預設（2026-08-12）。

    這個值來自 JSON body。正式環境有 `TTS_API_KEY` 擋著，但預設是「未設＝內網開發
    模式不驗」，而它會被組進 `os.path.join(TTS_VOICE_CACHE_DIR, f"voice-{elder_id}.wav")`
    ——含 `..` 或 `/` 就寫得出快取目錄之外。業務主鍵本來就是 uuid，收窄不影響正常使用。
    """
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")

    def must_not_download(_url, timeout=None):
        raise AssertionError("elder_id 不合法時不該連外下載")

    monkeypatch.setattr(tts_server.urllib.request, "urlopen", must_not_download)

    for bad in ("../../etc/passwd", "a/b", "e1 ", "x" * 65, "e1;rm"):
        assert tts_server._resolve_voice(bad, "https://example.test/v.wav", "逐字稿", "1") == (
            "/default.wav",
            "預設逐字稿",
        ), f"{bad!r} 不該被當成合法的 elder_id"
    assert tts_server._voice_cache == {}


def test_resolve_voice_rejects_a_non_http_reference_url(monkeypatch, tmp_path):
    """參考音檔網址只接受 http(s)：`urlopen` 也吃得下 `file://`（2026-08-12）。"""
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")

    def must_not_download(_url, timeout=None):
        raise AssertionError("非 http(s) 網址不該送進 urlopen")

    monkeypatch.setattr(tts_server.urllib.request, "urlopen", must_not_download)

    assert tts_server._resolve_voice("e1", "file:///etc/passwd", "逐字稿", "1") == (
        "/default.wav",
        "預設逐字稿",
    )


def test_resolve_voice_falls_back_when_download_fails(monkeypatch, tmp_path):
    """下載失敗只犧牲客製化聲音，不能讓整輪沒聲音（2026-08-01）。

    原本 urlopen 未接例外：網址過期／Supabase 不通都會讓 /synthesize 回 500，
    應用層據此退化成純文字——長輩完全聽不到聲音，而且每輪重複發生（快取永遠暖不起來）。
    客製化聲音失效是缺憾，沒聲音是故障，兩者嚴重度差一級。
    """
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")

    def boom(_url, timeout=None):
        raise OSError("HTTP Error 400: Bad Request")  # 簽章網址過期時 Supabase 的回應

    monkeypatch.setattr(tts_server.urllib.request, "urlopen", boom)

    assert tts_server._resolve_voice("e1", "https://expired.test/v.wav", "逐字稿") == (
        "/default.wav",
        "預設逐字稿",
    )


def test_resolve_voice_does_not_cache_a_failed_download(monkeypatch, tmp_path):
    """失敗不入快取：下次（例如網址已換發）要能再試，否則一次失敗就永久退化。"""
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")

    attempts = []

    def flaky(url, timeout=None):
        attempts.append(url)
        if len(attempts) == 1:
            raise OSError("暫時失敗")
        return _FakeHttpResponse(b"WAVDATA")

    # 轉檔以替身代替：本測試的對象是下載與快取邏輯，不是 ffmpeg
    # （單元測試環境沒有 ffmpeg，真正的正規化另有專門的測試）。
    monkeypatch.setattr(
        tts_server, "_normalize_to_wav", lambda audio, dest: pathlib.Path(dest).write_bytes(audio)
    )
    monkeypatch.setattr(tts_server.urllib.request, "urlopen", flaky)

    first = tts_server._resolve_voice("e1", "https://x.test/v.wav", "逐字稿")
    assert first == ("/default.wav", "預設逐字稿")

    second = tts_server._resolve_voice("e1", "https://x.test/v.wav", "逐字稿")
    assert second == (str(tmp_path / "voice-e1.wav"), "逐字稿")
    assert len(attempts) == 2


# --- 逐請求合成逾時（2026-08-09） ---


@pytest.fixture()
def _reset_stuck(monkeypatch):
    """每個測試從 0 條放生執行緒開始（模組層計數，不重置會互相汙染）。"""
    monkeypatch.setattr(tts_server, "_stuck_workers", 0)


def test_synthesize_times_out_instead_of_holding_the_slot_forever(monkeypatch, _reset_stuck):
    """模型卡死時要回 504，而不是讓請求永遠掛著。

    沒有這道上限的話，一次卡死就佔走 semaphore 名額（預設只有 1 個），
    之後所有長輩都拿不到名額——整台服務不再產出任何語音，且不會自行恢復。
    """
    import time

    monkeypatch.setattr(tts_server, "TTS_SYNTH_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        tts_server, "_synthesize", lambda *_a: time.sleep(5) or (b"never-returns", 0)
    )

    res = TestClient(tts_server.app).post("/synthesize", json={"text": "阿嬤您好"})

    assert res.status_code == 504
    assert res.json()["detail"] == "synthesis_timeout"


def test_the_slot_is_released_so_later_requests_still_work(monkeypatch, _reset_stuck):
    """逾時後名額必須讓出來——這才是這道上限存在的理由。

    只驗「回 504」是不夠的：即使回了 504，若名額沒釋放，下一個請求照樣卡死。
    故先讓一個請求逾時，再送一個正常請求，斷言它拿得到名額並成功。
    """
    import time

    monkeypatch.setattr(tts_server, "TTS_SYNTH_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(tts_server, "_synthesize", lambda *_a: time.sleep(5) or (b"", 0))
    client = TestClient(tts_server.app)
    assert client.post("/synthesize", json={"text": "會卡住的那句"}).status_code == 504

    # 換成正常的合成：名額若沒讓出來，這一句會再度逾時（或永遠等待）。
    # ⚠️ 逾時要一併放寬（同 test_services_asr_server 的那條，2026-08-12）：0.05 秒是
    # 給上面那個卡死請求用的，留著會讓這個瞬間就回的請求也吃同一道預算——跑完整套
    # 測試時執行緒池被前面幾條刻意放生的 5 秒睡眠佔著，光是排到就可能超過 50ms。
    # 這裡要驗的是名額有沒有讓出來，不是第二個請求有多快。
    monkeypatch.setattr(tts_server, "TTS_SYNTH_TIMEOUT_SECONDS", 30.0)
    monkeypatch.setattr(tts_server, "_synthesize", lambda *_a: (b"ok-m4a", 900))
    res = client.post("/synthesize", json={"text": "後續的長輩"})

    assert res.status_code == 200
    assert res.content == b"ok-m4a"


def test_healthz_reports_degraded_after_a_timeout(monkeypatch, _reset_stuck):
    """放生的執行緒只能靠重啟回收，故 healthz 要講實話讓維運看得見。

    先前 healthz 只看模型載入與否：服務癱瘓時它依然回 ok，監控全綠，
    只有長輩發現金孫不說話了。
    """
    import time

    client = TestClient(tts_server.app)
    assert client.get("/healthz").json()["status"] == "ok"

    monkeypatch.setattr(tts_server, "TTS_SYNTH_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(tts_server, "_synthesize", lambda *_a: time.sleep(5) or (b"", 0))
    client.post("/synthesize", json={"text": "會卡住的那句"})

    body = client.get("/healthz").json()
    assert body["status"] == "degraded"
    assert body["stuck_workers"] == 1


def test_ffmpeg_conversion_has_a_timeout(monkeypatch):
    """ffmpeg 是子行程、殺得掉，故直接給 subprocess.run 逾時即可真正回收。"""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        raise AssertionError("只驗參數，不實際執行")

    monkeypatch.setattr(tts_server.subprocess, "run", fake_run)
    with pytest.raises(AssertionError):
        tts_server._wav_to_m4a(b"RIFF")

    assert seen["timeout"] == tts_server.TTS_FFMPEG_TIMEOUT_SECONDS


def test_voice_download_has_a_timeout(monkeypatch, tmp_path):
    """參考音檔下載是對外網路呼叫，不設上限同樣會佔住名額。"""
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    seen = {}

    def fake_urlopen(url, timeout=None):
        seen["timeout"] = timeout
        return _FakeHttpResponse(b"WAVDATA")

    monkeypatch.setattr(tts_server.urllib.request, "urlopen", fake_urlopen)
    tts_server._resolve_voice("e1", "https://x.test/v.wav", "逐字稿")

    assert seen["timeout"] == tts_server.TTS_VOICE_DOWNLOAD_TIMEOUT_SECONDS


# --- 參考音檔正規化（2026-08-11） ---


def test_reference_audio_is_normalized_to_16k_mono_wav(monkeypatch):
    """家屬用瀏覽器錄音，MediaRecorder 產出 webm/opus，而 CosyVoice 讀檔走
    soundfile（libsndfile）——**它讀不了 webm**。不轉檔的話家屬明明錄好了，
    合成時卻會在讀檔那一步爆掉。取樣率與聲道數也隨裝置而異，一併統一。
    """
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

    monkeypatch.setattr(tts_server.subprocess, "run", fake_run)
    tts_server._normalize_to_wav(b"WEBMDATA", "/tmp/out.wav")

    cmd = seen["cmd"]
    assert cmd[0] == "ffmpeg"
    assert cmd[-1] == "/tmp/out.wav"
    assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "1", "單聲道"
    assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == str(tts_server._VOICE_TARGET_SR)
    assert seen["kwargs"]["input"] == b"WEBMDATA"
    assert seen["kwargs"]["check"] is True, "轉檔失敗要拋出來，讓上層退回全域預設聲音"
    assert seen["kwargs"]["timeout"] == tts_server.TTS_FFMPEG_TIMEOUT_SECONDS


def test_a_recording_ffmpeg_cannot_read_falls_back_to_the_global_voice(monkeypatch, tmp_path):
    """轉檔失敗與下載失敗對長輩的後果相同（聽到預設聲音），故走同一條退路。

    ⚠️ 也不可以入快取：家屬重錄之後要能再試一次。
    """
    import subprocess

    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")
    monkeypatch.setattr(
        tts_server.urllib.request,
        "urlopen",
        lambda url, timeout=None: _FakeHttpResponse(b"NOT-AUDIO"),
    )

    def boom(audio, dest):
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(tts_server, "_normalize_to_wav", boom)

    assert tts_server._resolve_voice("e1", "https://x.test/v.webm", "逐字稿") == (
        "/default.wav",
        "預設逐字稿",
    )
    assert tts_server._voice_cache == {}, "失敗不可入快取，否則家屬重錄也救不回來"
