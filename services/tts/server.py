"""DGX 端 TTS 推論服務（CosyVoice 3）：提供 POST /synthesize、GET /healthz。

僅在 DGX（Linux + ARM64 + GPU）執行；安裝見 services/tts/requirements.txt。
啟動：uvicorn services.tts.server:app --host 0.0.0.0 --port 8002

與 kinsun.speech.tts.DgxTtsClient 的契約：
- 輸入：JSON {"text": ..., "elder_id"?: ..., "prompt_audio_url"?: ..., "prompt_text"?: ...}。
  後三個欄位選填，用於每位長輩客製化聲音複製（2026-07-30）：帶 elder_id 且本機
  已快取該長輩的參考音檔時，直接沿用快取；快取沒有則需同時帶 prompt_audio_url／
  prompt_text 下載一次並快取；三者皆缺（或缺 elder_id）則沿用下方全域預設聲音。
- 輸出：m4a（AAC）bytes、Content-Type: audio/mp4、header X-Duration-Ms。

zero-shot 聲音複製：TTS_PROMPT_WAV（參考音檔）＋ TTS_PROMPT_TEXT（其逐字稿），
此為缺 elder_id 客製聲音時的全域預設值。

DGX 實機鎖定（2026-07-02，GB10 / aarch64 / CUDA 13）：
- CosyVoice repo 非 pip 套件，須把 repo 與其 third_party/Matcha-TTS 加入 sys.path
  （TTS_COSY_DIR／TTS_MATCHA_DIR）。
- aarch64 上 torchaudio 的 load/save 會強走 torchcodec（.so 載不起來）→ 以 soundfile 包一層。
- 用 AutoModel 依模型目錄自動判別（Fun-CosyVoice3-0.5B-2512 → CosyVoice3）。
- zero-shot 逐字稿須加 instruct 前綴 "You are a helpful assistant.<|endofprompt|>"，
  否則 LLM 會立刻 EOS、產不出語音。
"""

from __future__ import annotations

import asyncio
import hmac
import io
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

logger = logging.getLogger(__name__)

TTS_MODEL_ID = os.environ.get("TTS_MODEL_ID", "FunAudioLLM/Fun-CosyVoice3-0.5B-2512")
TTS_COSY_DIR = os.environ.get("TTS_COSY_DIR", "")
TTS_MATCHA_DIR = os.environ.get("TTS_MATCHA_DIR", "")
TTS_PROMPT_WAV = os.environ.get("TTS_PROMPT_WAV", "")
TTS_PROMPT_TEXT = os.environ.get("TTS_PROMPT_TEXT", "")
TTS_MAX_CONCURRENCY = int(os.environ.get("TTS_MAX_CONCURRENCY", "1"))
TTS_MAX_QUEUE = int(os.environ.get("TTS_MAX_QUEUE", "8"))
# 單一請求的合成時間上限（秒）。⚠️ 預設刻意寬鬆：GPU 下長回覆約 8 秒，但 GPU 被別人
# 佔滿時本服務會降級跑 CPU（RTF 13～16，同樣的話要 60～70 秒），預設值若照 GPU 抓，
# 降級模式會變成每一句都逾時。長輩那端本來就有自己的 30 秒上限（TTS_TIMEOUT_SECONDS），
# 這裡的目的不是控制長輩等多久，而是**不讓卡死的請求永久佔住併發名額**。
TTS_SYNTH_TIMEOUT_SECONDS = float(os.environ.get("TTS_SYNTH_TIMEOUT_SECONDS", "120"))
# 參考音檔下載逾時（秒）：對外網路呼叫，不設上限同樣會佔住名額。
TTS_VOICE_DOWNLOAD_TIMEOUT_SECONDS = float(
    os.environ.get("TTS_VOICE_DOWNLOAD_TIMEOUT_SECONDS", "15")
)
# wav→m4a 的 ffmpeg 逾時（秒）：子行程殺得掉，逾時即回收。
TTS_FFMPEG_TIMEOUT_SECONDS = float(os.environ.get("TTS_FFMPEG_TIMEOUT_SECONDS", "30"))
# 合成文字長度上限（✅ D-26 乙-7）：缺 text 原本會靜默合成空音，改 400。
TTS_MAX_TEXT_CHARS = int(os.environ.get("TTS_MAX_TEXT_CHARS", "1000"))
# 共用金鑰（✅ D-56 丙-10）：設定後驗 X-Api-Key；未設＝內網開發模式不驗。
TTS_API_KEY = os.environ.get("TTS_API_KEY", "")
TTS_PRELOAD = os.environ.get("TTS_PRELOAD", "0").strip().lower() not in {"0", "false", "no", ""}
# 每位長輩客製化參考語音的本機快取（2026-07-30）：下載一次後重複使用，避免每輪都重下載。
TTS_VOICE_CACHE_DIR = os.environ.get("TTS_VOICE_CACHE_DIR", tempfile.gettempdir())
TTS_VOICE_CACHE_SIZE = int(os.environ.get("TTS_VOICE_CACHE_SIZE", "20"))

# zero-shot 逐字稿的 instruct 前綴（見模組 docstring 的 DGX 鎖定說明）。
_INSTRUCT_PREFIX = "You are a helpful assistant.<|endofprompt|>"

_model = None
_sem = asyncio.Semaphore(TTS_MAX_CONCURRENCY)
_inflight = 0
# 合成逾時後「放生」的執行緒數（2026-08-09）。
#
# ⚠️ 為什麼需要這個計數：Python **殺不掉執行緒**。合成跑在 threadpool 裡，逾時只能讓
# 等待的協程放棄、把 semaphore 名額讓出來，那條執行緒仍在背景跑、仍握著 GPU。
# 也就是說逾時**不是完全的復原**——服務能繼續接客，但每多一條放生的執行緒，就多一份
# 與新請求搶 GPU 的壓力，且 threadpool 的工作者數量有限，累積下去終究會耗盡。
#
# 真正的回收手段只有重啟行程。故把它累計起來並在 /healthz 顯示：讓維運看得見
# 「這台需要重啟了」，而不是像現在這樣——服務癱瘓、healthz 照樣回 ok、沒人知道。
_stuck_workers = 0
# elder_id -> (本機 wav 路徑, 逐字稿)；簡單 FIFO 上限淘汰，不需要真正的 LRU。
_voice_cache: dict[str, tuple[str, str]] = {}


def _resolve_voice(elder_id: str, prompt_audio_url: str, prompt_text: str) -> tuple[str, str]:
    """依 elder_id 解析客製化參考語音；缺 elder_id 或無法取得時退回全域預設聲音。"""
    if not elder_id:
        return TTS_PROMPT_WAV, TTS_PROMPT_TEXT
    cached = _voice_cache.get(elder_id)
    if cached is not None:
        return cached
    if not prompt_audio_url or not prompt_text:
        return TTS_PROMPT_WAV, TTS_PROMPT_TEXT
    local_path = os.path.join(TTS_VOICE_CACHE_DIR, f"voice-{elder_id}.wav")
    # 下載失敗退回全域預設聲音（2026-08-01）：原本不接例外，於是任何下載問題（網址過期、
    # Supabase 暫時不通、磁碟寫入失敗）都會讓 /synthesize 回 500 → 應用層退化成純文字，
    # **長輩整輪完全聽不到聲音**，而且每輪重複發生（快取永遠暖不起來）。
    # 客製化聲音失效是缺憾，沒聲音是故障——兩者嚴重度差一級，不該混為一談。
    try:
        with urllib.request.urlopen(  # noqa: S310 - 內部/簽章 URL
            prompt_audio_url, timeout=TTS_VOICE_DOWNLOAD_TIMEOUT_SECONDS
        ) as resp:
            with open(local_path, "wb") as fh:
                fh.write(resp.read())
    except Exception:
        # 記到 ERROR：這是「長輩專屬的聲音沒生效」，不是可以忽略的雜訊。
        logger.error(
            "客製化參考語音下載失敗，改用全域預設聲音 elder_id=%s", elder_id, exc_info=True
        )
        return TTS_PROMPT_WAV, TTS_PROMPT_TEXT
    if len(_voice_cache) >= TTS_VOICE_CACHE_SIZE:
        _voice_cache.pop(next(iter(_voice_cache)))
    _voice_cache[elder_id] = (local_path, prompt_text)
    return local_path, prompt_text


def _install_soundfile_shim() -> None:
    """aarch64：用 soundfile 取代 torchaudio 的 load/save（torchcodec .so 載不起來）。"""
    import soundfile as sf
    import torch
    import torchaudio

    def _sf_load(filepath, *a, **k):
        data, srate = sf.read(str(filepath), dtype="float32", always_2d=True)
        return torch.from_numpy(data.T).contiguous(), srate

    def _sf_save(filepath, src, sample_rate, *a, **k):
        sf.write(str(filepath), src.detach().cpu().numpy().T, sample_rate)

    torchaudio.load = _sf_load
    torchaudio.save = _sf_save


def _get_model():
    """延遲載入 CosyVoice 3；缺參考語音或 repo 路徑設定即明確報錯。"""
    global _model
    if _model is None:
        if not TTS_PROMPT_WAV or not TTS_PROMPT_TEXT:
            raise RuntimeError("需設定 TTS_PROMPT_WAV 與 TTS_PROMPT_TEXT（金孫參考語音）")
        if not TTS_COSY_DIR:
            raise RuntimeError("需設定 TTS_COSY_DIR（CosyVoice repo 目錄）")
        matcha_dir = TTS_MATCHA_DIR or os.path.join(TTS_COSY_DIR, "third_party", "Matcha-TTS")
        for path in (matcha_dir, TTS_COSY_DIR):
            if path not in sys.path:
                sys.path.insert(0, path)
        _install_soundfile_shim()
        from cosyvoice.cli.cosyvoice import AutoModel

        _model = AutoModel(model_dir=TTS_MODEL_ID)
    return _model


def _synthesize(text: str, prompt_wav: str, prompt_text: str) -> tuple[bytes, int]:
    import soundfile as sf
    import torch

    model = _get_model()
    prompt = f"{_INSTRUCT_PREFIX}{prompt_text}"
    chunks = [
        out["tts_speech"]
        for out in model.inference_zero_shot(text, prompt, prompt_wav, stream=False)
    ]
    if not chunks:
        raise RuntimeError("CosyVoice 3 未產出任何語音段")
    waveform = torch.cat(chunks, dim=1)  # [1, N]
    sample_rate = int(model.sample_rate)
    duration_ms = int(waveform.shape[1] / sample_rate * 1000)

    wav_buf = io.BytesIO()
    sf.write(wav_buf, waveform.detach().cpu().numpy().T, sample_rate, format="WAV")
    return _wav_to_m4a(wav_buf.getvalue()), duration_ms


def _wav_to_m4a(wav_bytes: bytes) -> bytes:
    """DGX 端 ffmpeg：wav → AAC/m4a（應用層跨平台、不裝 ffmpeg）。

    mp4/m4a 的 moov atom 需可 seek 的輸出，直接寫 pipe:1 會失敗
    （muxer does not support non seekable output）→ 走可 seek 的暫存檔再讀回。
    """
    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        # timeout 與合成那道不同：子行程**殺得掉**，逾時會送 SIGKILL 並拋
        # TimeoutExpired，資源真的回收得掉，不會留下背景殘骸。
        subprocess.run(
            ["ffmpeg", "-y", "-f", "wav", "-i", "pipe:0", "-c:a", "aac", tmp_path],
            input=wav_bytes,
            capture_output=True,
            check=True,
            timeout=TTS_FFMPEG_TIMEOUT_SECONDS,
        )
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(tmp_path)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if TTS_PRELOAD:
        _get_model()
    yield


app = FastAPI(title="KinSun TTS (CosyVoice 3)", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    """⚠️ `status` 會在有放生執行緒時轉 `degraded`（2026-08-09）。

    先前只回報模型有沒有載入，於是「合成卡死、併發名額被永久佔走、整台服務不再
    產出任何語音」這個狀態下，healthz 依然一路回 ok——監控全綠，只有長輩發現
    金孫不說話了。放生的執行緒只能靠重啟行程回收，故這裡要講實話。
    """
    return {
        "status": "degraded" if _stuck_workers else "ok",
        "model_loaded": _model is not None,
        "stuck_workers": _stuck_workers,
    }


def _require_api_key(request: Request) -> None:
    if not TTS_API_KEY:
        return
    if not hmac.compare_digest(request.headers.get("x-api-key", ""), TTS_API_KEY):
        raise HTTPException(status_code=401, detail="invalid_api_key")


@app.post("/synthesize")
async def synthesize(payload: dict, request: Request) -> Response:
    global _inflight, _stuck_workers
    _require_api_key(request)
    # 基本請求驗證（✅ D-26 乙-7）：缺 text 400（原本靜默合成空音）、過長 413。
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="missing_text")
    if len(text) > TTS_MAX_TEXT_CHARS:
        raise HTTPException(status_code=413, detail="text_too_long")
    if _inflight >= TTS_MAX_CONCURRENCY + TTS_MAX_QUEUE:
        raise HTTPException(status_code=503, detail="overloaded")
    elder_id = str(payload.get("elder_id", "")).strip()
    prompt_audio_url = str(payload.get("prompt_audio_url", "")).strip()
    prompt_text_override = str(payload.get("prompt_text", "")).strip()
    _inflight += 1
    try:
        async with _sem:
            # ⚠️ 逾時的意義是「不再等它、把併發名額讓出來」，**不是**中止合成——
            # Python 殺不掉執行緒，那條工作者仍在背景跑、仍握著 GPU（見 _stuck_workers）。
            # 沒有這道上限的話，一次模型卡死就等於這台服務永久癱瘓：名額只有
            # TTS_MAX_CONCURRENCY 個（預設 1），被佔走就再也沒人拿得到，
            # 而 /healthz 只看模型載入與否，會一路回報 ok。
            try:
                prompt_wav, prompt_text = await asyncio.wait_for(
                    run_in_threadpool(
                        _resolve_voice, elder_id, prompt_audio_url, prompt_text_override
                    ),
                    timeout=TTS_SYNTH_TIMEOUT_SECONDS,
                )
                audio, duration_ms = await asyncio.wait_for(
                    run_in_threadpool(_synthesize, text, prompt_wav, prompt_text),
                    timeout=TTS_SYNTH_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                _stuck_workers += 1
                logger.error(
                    "合成逾時 %.0f 秒，已讓出併發名額但該執行緒仍在背景執行"
                    "（累計放生 %d 條，需重啟行程才能回收）elder_id=%s 字數=%d",
                    TTS_SYNTH_TIMEOUT_SECONDS,
                    _stuck_workers,
                    elder_id or "(全域預設聲音)",
                    len(text),
                )
                raise HTTPException(status_code=504, detail="synthesis_timeout") from None
    finally:
        _inflight -= 1
    return Response(
        content=audio,
        media_type="audio/mp4",
        headers={"X-Duration-Ms": str(duration_ms)},
    )
