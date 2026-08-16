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
import re
import subprocess
import sys
import tempfile
import urllib.request
import wave
from contextlib import asynccontextmanager, suppress

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
# elder_id -> (本機 wav 路徑, 逐字稿, 版本)；簡單 FIFO 上限淘汰，不需要真正的 LRU。
# 版本用來認出「家屬重錄過了」，見 `_resolve_voice`。
_voice_cache: dict[str, tuple[str, str, str]] = {}


# CosyVoice 參考音檔的目標格式。16k 單聲道與 ASR 端一致，也是 zero-shot 的常見輸入；
# 真正的重點不是這兩個數字，而是**不管家屬的裝置錄出什麼，進到模型的都是同一種東西**。
_VOICE_TARGET_SR = 16000

# `elder_id` 的合法字元（2026-08-12）。它來自請求 body，而且會被組進本機檔案路徑
# （`voice-<elder_id>.wav`）——含 `..` 或 `/` 就寫得出快取目錄之外。正式環境有
# `TTS_API_KEY` 擋著，但預設是「未設＝內網開發模式不驗」，所以這道不能省。
# 業務主鍵本來就是 uuid，收窄到這個字元集不影響任何正常呼叫。
_SAFE_ELDER_ID = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")


def _is_safe_elder_id(elder_id: str) -> bool:
    return bool(_SAFE_ELDER_ID.match(elder_id))


def _normalize_to_wav(audio: bytes, dest_path: str) -> None:
    """把任意容器的音檔正規化成 16k 單聲道 wav，寫到 dest_path。

    ⚠️ 為什麼非做不可：家屬用瀏覽器錄音，`MediaRecorder` 產出的是 webm/opus，
    而 CosyVoice 讀參考音檔走 soundfile（libsndfile）——**它讀不了 webm**。
    不轉檔的話，家屬明明錄好了，合成時卻會在讀檔那一步爆掉。

    ⚠️ 輸入一定要落地成**可 seek 的暫存檔**，不能用 `-i pipe:0`（2026-08-12 實測修正）：
    m4a 的 moov atom（索引）在檔尾，pipe 倒不回去，ffmpeg 會 demux 失敗——
    但**它以離開碼 0 結束**，於是 `check=True` 攔不到，靜默產出一個只有檔頭、
    零取樣的 wav。這正是 services/asr 早已解過的同一個問題。

    此處原本的註解推論「輸入來源是我們自己的 bucket，格式不受 LINE 那類外部來源限制」，
    **那個前提是錯的**：家屬用 iPhone 錄音上傳就是 m4a。實測（DGX，同一個檔案）：

        -i pipe:0      → 離開碼 0，產出 114 bytes（空 wav）
        -i <暫存檔>    → 離開碼 0，產出 288882 bytes

    ⚠️ 轉完必須檢查真的有取樣：ffmpeg 離開碼 0 不等於輸出可用（如上）。少了這道檢查，
    空 wav 會被當成轉檔成功、連快取都記下來，一路送到 CosyVoice 才炸成 500，
    應用層退化成純文字——**長輩整輪完全聽不到聲音，而且每輪重複**。
    在這裡拋例外，呼叫端的 except 才會把它降級成「改用全域預設聲音」，
    也就是原本就設計好的那條退路：客製化聲音失效是缺憾，沒聲音是故障。
    """
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp.write(audio)
        src_path = tmp.name
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                src_path,
                "-ac",
                "1",
                "-ar",
                str(_VOICE_TARGET_SR),
                dest_path,
            ],
            capture_output=True,
            check=True,
            timeout=TTS_FFMPEG_TIMEOUT_SECONDS,
        )
    finally:
        with suppress(OSError):
            os.unlink(src_path)
    # 用標準函式庫的 wave 而非 soundfile：輸出格式是我們自己指定的 pcm wav，wave 讀得動，
    # 而且它在應用層的測試環境也在（soundfile 只裝在本服務的 venv，用它會讓這裡無法離線測試）。
    with wave.open(dest_path, "rb") as wav:
        frames = wav.getnframes()
    if frames == 0:
        raise ValueError(f"轉檔後沒有任何取樣（來源 {len(audio)} bytes，可能是檔案損毀或截斷）")


def _resolve_voice(
    elder_id: str, prompt_audio_url: str, prompt_text: str, prompt_version: str = ""
) -> tuple[str, str]:
    """依 elder_id 解析客製化參考語音；缺 elder_id 或無法取得時退回全域預設聲音。

    ⚠️ `prompt_version` 決定「要不要重新下載」（2026-08-12）。原本快取只認 elder_id、
    命中就直接回傳，連新的 `prompt_audio_url` 都不看——於是家屬重錄之後（`PUT` 覆蓋
    bucket 內同一個物件路徑，路徑本身不會變），DGX 端仍然拿第一次下載的那份錄音合成，
    要等 `TTS_VOICE_CACHE_SIZE` 位長輩把它擠出快取、或整個服務重啟才會換。**全程沒有
    任何錯誤訊息**，家屬只會覺得「我明明重錄了怎麼沒變」，而這正是這個功能的主要操作。

    版本由應用層帶入，值是 `voice_profiles.granted_at`（見 `VoiceReference.version`）。
    """
    if not _is_safe_elder_id(elder_id):
        if elder_id:  # 空字串是正常情形（沒有客製化聲音），不必吵
            logger.error(
                "elder_id 格式不合法，改用全域預設聲音 elder_id=%r",
                elder_id[:64],
            )
        return TTS_PROMPT_WAV, TTS_PROMPT_TEXT
    cached = _voice_cache.get(elder_id)
    if cached is not None and cached[2] == prompt_version:
        return cached[0], cached[1]
    if not prompt_audio_url or not prompt_text:
        # 版本對不上卻沒帶網址：無從更新。有舊的就先用舊的——這條路在正常流程走不到
        # （應用層一律網址與版本一起送），寧可聲音舊一點，也不要中途換成另一個人的聲音。
        if cached is not None:
            return cached[0], cached[1]
        return TTS_PROMPT_WAV, TTS_PROMPT_TEXT
    if not prompt_audio_url.startswith(("http://", "https://")):
        # `urlopen` 也吃 file:// 與其他 scheme；參考音檔一律來自我們自己的 bucket。
        logger.error(
            "參考音檔網址不是 http(s)，改用全域預設聲音 elder_id=%s",
            elder_id,
        )
        return TTS_PROMPT_WAV, TTS_PROMPT_TEXT
    local_path = os.path.join(TTS_VOICE_CACHE_DIR, f"voice-{elder_id}.wav")
    # 下載失敗退回全域預設聲音（2026-08-01）：原本不接例外，於是任何下載問題（網址過期、
    # Supabase 暫時不通、磁碟寫入失敗）都會讓 /synthesize 回 500 → 應用層退化成純文字，
    # **長輩整輪完全聽不到聲音**，而且每輪重複發生（快取永遠暖不起來）。
    # 客製化聲音失效是缺憾，沒聲音是故障——兩者嚴重度差一級，不該混為一談。
    #
    # 正規化同樣包在這裡（2026-08-11）：家屬是用瀏覽器錄的，`MediaRecorder` 產出的是
    # **webm/opus**，而 CosyVoice 讀檔走 soundfile（libsndfile）——它讀不了 webm，
    # 直接餵進去會炸。取樣率與聲道數也隨裝置而異。故一律以 ffmpeg 轉成 16k 單聲道 wav。
    try:
        with urllib.request.urlopen(  # noqa: S310 - 內部/簽章 URL
            prompt_audio_url, timeout=TTS_VOICE_DOWNLOAD_TIMEOUT_SECONDS
        ) as resp:
            downloaded = resp.read()
        _normalize_to_wav(downloaded, local_path)
    except Exception:
        # 記到 ERROR：這是「長輩專屬的聲音沒生效」，不是可以忽略的雜訊。
        # 涵蓋下載與正規化兩種失敗——對長輩而言後果相同（聽到的是預設聲音），
        # 對維運而言 exc_info 會指出是哪一段。
        logger.error(
            "客製化參考語音取得失敗（下載或轉檔），改用全域預設聲音 elder_id=%s",
            elder_id,
            exc_info=True,
        )
        return TTS_PROMPT_WAV, TTS_PROMPT_TEXT
    while len(_voice_cache) >= TTS_VOICE_CACHE_SIZE:
        _evict_oldest_voice()
    _voice_cache[elder_id] = (local_path, prompt_text, prompt_version)
    return local_path, prompt_text


def _evict_oldest_voice() -> None:
    """淘汰最舊的一筆快取，**連本機檔案一起刪掉**（2026-08-12）。

    這些是長輩家人的聲音樣本，不是可以無限期堆在暫存目錄的中介檔。淘汰之後那個檔案
    再也不會被讀到（下次同一位長輩來會重新下載），留著只是佔磁碟並擴大外洩面。
    刪不掉不影響合成，記 warning 就好。
    """
    oldest = next(iter(_voice_cache))
    path, _text, _version = _voice_cache.pop(oldest)
    try:
        os.unlink(path)
    except OSError as exc:
        logger.warning("淘汰的參考音檔刪不掉 elder_id=%s path=%s：%s", oldest, path, exc)


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
    # 缺席＝舊版呼叫端（一律空字串）：行為與加入本欄位前相同，命中快取就沿用。
    prompt_version = str(payload.get("prompt_version", "")).strip()
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
                        _resolve_voice,
                        elder_id,
                        prompt_audio_url,
                        prompt_text_override,
                        prompt_version,
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
