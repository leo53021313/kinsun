# ASR 服務（Breeze-ASR-26）— DGX 端

語音轉文字（國台語 → 繁體國語漢字）推論服務。**僅在 DGX Spark 執行**（需 GPU 與 `transformers`／`torch`），不屬於應用層、不進開發機的測試套件。

## 與應用層的契約

| 項目 | 內容 |
|------|------|
| 路徑 | `POST /transcribe` |
| 請求 | body 為**原始音檔 bytes**（`Content-Type` 由呼叫端帶入，如 `audio/m4a`） |
| 回應 | JSON `{"text": "<繁體國語漢字>"}` |
| 呼叫端 | [`kinsun.speech.asr.DgxAsrClient`](../../kinsun/speech/asr.py) |

## 部署（DGX）

```bash
# 在 DGX 上，使用對應 aarch64/CUDA 的環境
pip install -r services/asr/requirements.txt
# 可用 ASR_MODEL_ID 覆寫模型 id（預設 MediaTek-Research/Breeze-ASR-26，需實機驗證）
uvicorn services.asr.server:app --host 0.0.0.0 --port 8001
```

## 接到應用層

在應用層的 `.env` 設定：

```dotenv
ASR_BACKEND=dgx
ASR_ENDPOINT=http://<dgx-host>:8001/transcribe
```

## 待辦（於 DGX 實機驗證）

- [ ] 確認 Breeze-ASR-26 的正確模型 id 與載入方式（必要時改用本地權重路徑）。
- [ ] 確認音檔格式與前處理（取樣率、聲道、`m4a`／`wav`）。
- [ ] 鎖定 `torch`／`transformers` 在 aarch64 + CUDA 的版本。
- [ ] 加上逾時、併發與健康檢查（`/healthz`）。
