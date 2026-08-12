"""DGX 端 ASR 推論服務：載入 Breeze-ASR-26，提供 POST /transcribe、GET /healthz。

僅在 DGX（Linux + ARM64 + GPU）執行；安裝見 services/asr/requirements.txt。
啟動：uvicorn services.asr.server:app --host 0.0.0.0 --port 8001

與 kinsun.speech.asr.DgxAsrClient 的契約：
- 輸入：HTTP body 為原始音檔 bytes（Content-Type 由呼叫端帶入）。
- 輸出：JSON {"text": "繁體國語漢字"}。
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import subprocess
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


class AudioDecodeError(Exception):
    """音檔 bytes 無法解碼成可辨識的聲音樣本（ffmpeg 失敗或 0 樣本）。"""


# Breeze-ASR-26（Whisper 系）輸入取樣率。
_TARGET_SR = 16000

ASR_MODEL_ID = os.environ.get("ASR_MODEL_ID", "MediaTek-Research/Breeze-ASR-26")
ASR_MAX_CONCURRENCY = int(os.environ.get("ASR_MAX_CONCURRENCY", "1"))
ASR_MAX_QUEUE = int(os.environ.get("ASR_MAX_QUEUE", "8"))
# 單一請求的辨識時間上限（秒）。預設寬鬆：長輩可上傳到 ASR_MAX_BYTES 的音檔，
# 在 GPU 吃緊時解碼＋推論會拉長；這道上限的目的不是控制長輩等多久
# （那是應用層 ASR_TIMEOUT_SECONDS 的事），而是**不讓卡死的請求永久佔住併發名額**。
ASR_TRANSCRIBE_TIMEOUT_SECONDS = float(os.environ.get("ASR_TRANSCRIBE_TIMEOUT_SECONDS", "120"))
# ffmpeg 解碼逾時（秒）：子行程殺得掉，逾時即回收。
ASR_FFMPEG_TIMEOUT_SECONDS = float(os.environ.get("ASR_FFMPEG_TIMEOUT_SECONDS", "30"))
# 單請求 body 上限（✅ D-26 乙-7）；預設 10MB 對齊主 API 對講機上限。
ASR_MAX_BODY_BYTES = int(os.environ.get("ASR_MAX_BODY_BYTES", "10485760"))
# 共用金鑰（✅ D-56 乙方向丙-10）：設定後驗 X-Api-Key；未設＝內網開發模式不驗。
ASR_API_KEY = os.environ.get("ASR_API_KEY", "")
# 靜音峰值閘（2026-07-18）：峰值低於此值（約 -60 dBFS）視為純靜音、不進模型。
# Whisper 系模型對靜音會確定性幻覺出重複語句（實錄「來，請坐…」迴圈），
# 一輪空跑約 10 秒 GPU；正常說話峰值遠高於此，誤殺風險極低。
ASR_SILENCE_PEAK = float(os.environ.get("ASR_SILENCE_PEAK", "0.001"))
# 釘死辨識語言（V-01，2026-07-29）——這是幻覺的**根因修正**，不是可有可無的調校。
#
# 模型的 generation_config 是 `forced_decoder_ids = [[1, None], [2, 50359]]`：
# 位置 2 釘住 `<|transcribe|>`（任務有交代），位置 1 的**語言槽卻是 None**（沒交代），
# 於是每一次請求都先跑一次自動語言偵測。音檔清楚時偵測得準；近無聲、或句尾帶一小段
# 靜音時偵測結果是垃圾，解碼隨即跑進退化迴圈。
#
# 實測（2026-07-29，真模型、同檔各跑 6 次）：
#   不釘語言 6/6 把 0.76 秒的「早安」辨識成「晴文」重複 60 次
#     ——同一句截到 0.68 秒反而正常，可見觸發點是**尾端那 0.08 秒的靜音**，不是音檔短
#   釘住語言 0/6，且白噪音從立陶宛人名「Vytautas」收斂成中文短字
# 那串幻覺文字會進危急分級器，實錄曾因此**真的送出假警報給家屬**。
#
# ⚠️ 空字串＝回到自動偵測（修正前行為），是就地回退的逃生口，不必重新部署程式。
# ⚠️ 副作用（已實測、判定可接受）：強制中文後，`blood pressure` 這類常見英文詞會被
# 寫成「血壓」而非保留原文；專有名詞（YouTube）仍保留。對本產品反而更好——危急關鍵詞
# 表與 LLM 都吃中文。
ASR_LANGUAGE = os.environ.get("ASR_LANGUAGE", "zh")
ASR_PRELOAD = os.environ.get("ASR_PRELOAD", "0") not in {"0", "false", "no"}

_model = None
_sem = asyncio.Semaphore(ASR_MAX_CONCURRENCY)
_inflight = 0
# 辨識逾時後「放生」的執行緒數（2026-08-11，與 services/tts 同一套處置）。
#
# ⚠️ Python 殺不掉執行緒：辨識跑在 threadpool，逾時只能讓等待的協程放棄、把
# semaphore 名額讓出來，那條工作者仍在背景跑、仍握著 GPU。逾時**不是完全的復原**。
#
# 真正的回收手段只有重啟行程，故累計並在 /healthz 顯示，讓維運看得見「這台需要重啟」。
# ⚠️ ASR 卡死比 TTS 更嚴重：TTS 掛了長輩至少還看得到文字回覆，ASR 掛了長輩連話都
# 送不進去——整個對講機形同斷線，而 healthz 先前只看模型載入與否、一路回報 ok。
_stuck_workers = 0


def _get_model():
    """延遲載入：無 GPU 的開發機不需安裝 transformers/torch。"""
    global _model
    if _model is None:
        import torch
        from transformers import pipeline as hf_pipeline

        # DGX 實機驗證（GB10）：不指定 device 會落 CPU、一句數十秒；GPU + fp16 才夠即時。
        use_cuda = torch.cuda.is_available()
        _model = hf_pipeline(
            "automatic-speech-recognition",
            model=ASR_MODEL_ID,
            device=0 if use_cuda else -1,
            torch_dtype=torch.float16 if use_cuda else torch.float32,
        )
    return _model


def _decode_to_mono16k(audio: bytes):
    """把任意容器的音檔 bytes 解成 16k 單聲道 float32 numpy 陣列。

    HF pipeline 內建的 ffmpeg_read 是把 bytes 灌進 ffmpeg stdin(pipe) 解碼；
    m4a 的 moov atom 在檔尾時 pipe 不可 seek 會解成 partial file → 失敗
    （LINE 語音多為此類 m4a）。改成寫可 seek 的暫存檔、自行以 ffmpeg 解碼，
    輸出 raw f32le 再包成 numpy 陣列餵給 pipeline（陣列會略過 ffmpeg_read）。
    """
    import numpy as np

    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp.write(audio)
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                tmp_path,
                "-ac",
                "1",
                "-ar",
                str(_TARGET_SR),
                "-f",
                "f32le",
                "pipe:1",
            ],
            capture_output=True,
            check=True,
            # 子行程**殺得掉**：逾時會送 SIGKILL 並拋 TimeoutExpired，資源真的回收得掉。
            # 與上面辨識那道逾時的性質不同（那裡只能讓出名額、殺不掉執行緒）。
            timeout=ASR_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("ffmpeg 解碼逾時 %.0f 秒，已終止子行程", ASR_FFMPEG_TIMEOUT_SECONDS)
        raise AudioDecodeError("ffmpeg_timeout") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        logger.error("ffmpeg 解碼失敗 exit=%s stderr=%s", exc.returncode, stderr)
        raise AudioDecodeError(f"ffmpeg exit {exc.returncode}") from exc
    finally:
        os.unlink(tmp_path)
    array = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if array.size == 0:
        logger.error("ffmpeg 解碼結果為 0 樣本（音檔無有效聲音內容）")
        raise AudioDecodeError("decoded_zero_samples")
    return array


def _transcribe(audio: bytes) -> str:
    array = _decode_to_mono16k(audio)
    if float(abs(array).max()) < ASR_SILENCE_PEAK:
        logger.info("進站音檔為純靜音（峰值 < %s），跳過辨識", ASR_SILENCE_PEAK)
        return ""
    payload = {"raw": array, "sampling_rate": _TARGET_SR}
    # 語言與任務成對指定：這是官方**非棄用**的作法（相對於直接改 forced_decoder_ids）。
    kwargs = (
        {"generate_kwargs": {"language": ASR_LANGUAGE, "task": "transcribe"}}
        if ASR_LANGUAGE
        else {}
    )
    result = _get_model()(payload, **kwargs)
    return result["text"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if ASR_PRELOAD:
        _get_model()
    yield


app = FastAPI(title="KinSun ASR (Breeze-ASR-26)", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    """⚠️ `status` 會在有放生執行緒時轉 `degraded`（2026-08-11）。

    先前只回報模型有沒有載入，於是「辨識卡死、併發名額被永久佔走、長輩連話都送不
    進去」這個狀態下，healthz 依然一路回 ok——監控全綠，對講機卻已形同斷線。
    放生的執行緒只能靠重啟行程回收，故這裡要講實話。
    """
    return {
        "status": "degraded" if _stuck_workers else "ok",
        "model_loaded": _model is not None,
        "stuck_workers": _stuck_workers,
    }


def _require_api_key(request: Request) -> None:
    if not ASR_API_KEY:
        return
    if not hmac.compare_digest(request.headers.get("x-api-key", ""), ASR_API_KEY):
        raise HTTPException(status_code=401, detail="invalid_api_key")


@app.post("/transcribe")
async def transcribe(request: Request) -> dict[str, str]:
    global _inflight, _stuck_workers
    _require_api_key(request)
    audio = await request.body()
    # 基本請求驗證（✅ D-26 乙-7）：空 body 400、超大 413，不進模型。
    if not audio:
        raise HTTPException(status_code=400, detail="missing_audio")
    if len(audio) > ASR_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="audio_too_large")
    if _inflight >= ASR_MAX_CONCURRENCY + ASR_MAX_QUEUE:
        raise HTTPException(status_code=503, detail="overloaded")
    _inflight += 1
    try:
        async with _sem:
            # ⚠️ 逾時的意義是「不再等它、把併發名額讓出來」，**不是**中止辨識——
            # Python 殺不掉執行緒，那條工作者仍在背景跑（見 _stuck_workers）。
            # 沒有這道上限的話，一次卡死就等於整台服務永久癱瘓：名額只有
            # ASR_MAX_CONCURRENCY 個（預設 1），被佔走就再也沒人拿得到，
            # 長輩從此連話都送不進去，而 /healthz 只看模型載入與否、會一路回 ok。
            try:
                text = await asyncio.wait_for(
                    run_in_threadpool(_transcribe, audio),
                    timeout=ASR_TRANSCRIBE_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                _stuck_workers += 1
                logger.error(
                    "辨識逾時 %.0f 秒，已讓出併發名額但該執行緒仍在背景執行"
                    "（累計放生 %d 條，需重啟行程才能回收）音檔 %d bytes",
                    ASR_TRANSCRIBE_TIMEOUT_SECONDS,
                    _stuck_workers,
                    len(audio),
                )
                raise HTTPException(status_code=504, detail="transcribe_timeout") from None
    except AudioDecodeError:
        # 壞音檔是呼叫端資料問題（4xx），不是服務故障（500）；根因已於 decode 記 log。
        raise HTTPException(status_code=422, detail="audio_decode_failed") from None
    finally:
        _inflight -= 1
    return {"text": text}
