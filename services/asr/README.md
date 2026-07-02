# ASR 服務（Breeze-ASR-26）— DGX 端

語音轉文字（國台語 → 繁體國語漢字）推論服務。**僅在 DGX Spark 執行**（需 GPU 與 `transformers`／`torch`），不屬於應用層、不進開發機的測試套件。

## 與應用層的契約

| 項目 | 內容 |
|------|------|
| 路徑 | `POST /transcribe` |
| 請求 | body 為**原始音檔 bytes**（`Content-Type` 由呼叫端帶入，如 `audio/m4a`） |
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

**系統需求：** `ffmpeg`（HF pipeline 解 `m4a`／非 `wav` 音檔的依賴）。

**環境變數：**

| 環境變數 | 預設 | 用途 |
|---|---|---|
| `ASR_MODEL_ID` | `MediaTek-Research/Breeze-ASR-26` | 覆寫模型 id |
| `ASR_MAX_CONCURRENCY` | `1` | 同時處理的辨識請求數（threadpool + semaphore） |
| `ASR_MAX_QUEUE` | `8` | 等候佇列上限，超過回 503 |
| `ASR_PRELOAD` | `0` | 設 `1` 於服務啟動（lifespan）即載入模型，預設延遲載入 |

> DGX Spark（GB10）實機驗證：不指定 device 會落在 CPU、一句數十秒；GPU + fp16 才夠即時（真人聲實測約 1.1 秒）。
> `server.py` 已依此鎖定 `device=0`／`torch.float16`（無 GPU 時退回 CPU／fp32，供開發機無 GPU 情境使用）。

## 接到應用層

在應用層的 `.env` 設定：

```dotenv
ASR_BACKEND=dgx
ASR_ENDPOINT=http://<dgx-host>:8001/transcribe
```

## 待辦（於 DGX 實機驗證）

- [x] 確認 Breeze-ASR-26 的正確模型 id 與載入方式——已於 DGX（GB10）實機驗證，模型 id 正確、GPU + fp16 可即時辨識真人聲。
- [x] 確認音檔格式與前處理（取樣率、聲道、`m4a`／`wav`）——已補系統需求 `ffmpeg`（HF pipeline 解碼依賴）。
- [ ] 鎖定 `torch`／`transformers` 在 aarch64 + CUDA 的正式版本並寫入 `requirements.txt`（實機已知可用：`torch` aarch64/CUDA PyPI 輪子可直接安裝）。
- [x] 加上逾時、併發與健康檢查（`GET /healthz`）——已於程式碼實作（threadpool + semaphore + 佇列上限 503）。
