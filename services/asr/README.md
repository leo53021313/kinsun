# ASR 服務（Breeze-ASR-26）— DGX 端

語音轉文字（國台語 → 繁體國語漢字）推論服務。**僅在 DGX Spark 執行**（需 GPU 與 `transformers`／`torch`），不屬於應用層、不進開發機的測試套件。

## 與應用層的契約

| 項目 | 內容 |
|------|------|
| 路徑 | `POST /transcribe` |
| 請求 | body 為**原始音檔 bytes**（`Content-Type` 由呼叫端帶入，如 `audio/m4a`；容器不拘） |
| 回應 | JSON `{"text": "<繁體國語漢字>"}` |
| 健康檢查 | `GET /healthz` → `{"status": "ok", "model_loaded": <bool>}` |
| 過載 | 等候請求數超過 `ASR_MAX_CONCURRENCY + ASR_MAX_QUEUE` → 回 503 |
| 呼叫端 | [`kinsun.speech.asr.DgxAsrClient`](../../src/kinsun/speech/asr.py) |

## 部署（DGX）

```bash
# 在 DGX 上，使用對應 aarch64/CUDA 的環境
pip install -r services/asr/requirements.txt
# 可用 ASR_MODEL_ID 覆寫模型 id（預設 MediaTek-Research/Breeze-ASR-26，已於 DGX 實機驗證模型 id 正確）
uvicorn services.asr.server:app --host 0.0.0.0 --port 8001
```

**系統需求：** `ffmpeg`。服務**自行**以 ffmpeg 把音檔 bytes 解成 16k 單聲道 f32le 陣列再餵給
pipeline——因為 HF 內建的 `ffmpeg_read` 是把 bytes 灌進 ffmpeg `stdin`（pipe，不可 seek），
而 `moov` atom 在檔尾的 m4a（LINE 語音多為此類）在 pipe 上只會解成 partial file 而失敗；
改走可 seek 的暫存檔即可正確解碼任意容器（m4a／wav／ogg…）。

**環境變數：**

| 環境變數 | 預設 | 用途 |
|---|---|---|
| `ASR_MODEL_ID` | `MediaTek-Research/Breeze-ASR-26` | 覆寫模型 id |
| `ASR_MAX_CONCURRENCY` | `1` | 同時處理的辨識請求數（threadpool + semaphore） |
| `ASR_MAX_QUEUE` | `8` | 等候佇列上限，超過回 503 |
| `ASR_PRELOAD` | `0` | 設 `1` 於服務啟動（lifespan）即載入模型，預設延遲載入 |

> DGX Spark（GB10）實機驗證：不指定 device 會落在 CPU、一句數十秒；GPU + fp16 才夠即時（真人聲實測約 1.1 秒）。
> `server.py` 已依此鎖定 `device=0`／`torch.float16`（無 GPU 時退回 CPU／fp32，供開發機無 GPU 情境使用）。
> 2026-07-02 端到端實機：把 CosyVoice 3 合成的 m4a 餵入本服務，辨識回近乎一致的文字
> （torch 2.12.1+cu130、transformers 5.x）。

## 接到應用層

在應用層的 `.env` 設定：

```dotenv
ASR_BACKEND=dgx
ASR_ENDPOINT=http://<dgx-host>:8001/transcribe
```

## 待辦（於 DGX 實機驗證）

- [x] 確認 Breeze-ASR-26 的正確模型 id 與載入方式——已於 DGX（GB10）實機驗證，模型 id 正確、GPU + fp16 可即時辨識真人聲。
- [x] 確認音檔格式與前處理（取樣率、聲道、`m4a`／`wav`）——服務自行以 ffmpeg 解成 16k 單聲道陣列（見上），已實機驗證 m4a 可正確辨識。
- [x] 鎖定 `torch`／`transformers` 在 aarch64 + CUDA 的版本（`requirements.txt`：torch 2.12.1+cu130、transformers 5.x）。
- [x] 加上併發與健康檢查（`GET /healthz`）——已於程式碼實作（threadpool + semaphore + 佇列上限 503）。
- [ ] 服務端逐請求 timeout（目前僅呼叫端 `DgxAsrClient` 有 urlopen 逾時）。
