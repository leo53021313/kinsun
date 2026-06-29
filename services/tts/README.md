# TTS 服務（台語 TTS）— DGX 端

文字轉語音（繁體國語漢字 → 台語語音）推論服務。**僅在 DGX Spark 執行**（需 GPU 與 TTS 引擎），不屬於應用層、不進開發機的測試套件。

> 狀態：**骨架（placeholder）**。台語 TTS 模型尚未選定／訓練；本服務先固定契約與部署形狀，模型就緒後只換 `server.py` 的合成實作，應用層不動。

## 與應用層的契約

| 項目 | 內容 |
|------|------|
| 路徑 | `POST /synthesize` |
| 請求 | JSON `{"text": "<繁體國語漢字>"}` |
| 回應 | 原始音檔 bytes（`Content-Type: audio/wav`） |
| 呼叫端 | `kinsun.speech.tts.DgxTtsClient`（**尚未實作**；現為 placeholder [`TextBubbleTts`](../../src/kinsun/speech/tts.py)） |

> 對應的 `DgxTtsClient` 會把音檔 bytes 包成 `TtsResult(text=text, audio=<bytes>)`，介面與現有 `TTSClient.synthesize(text) -> TtsResult` 一致。

## 部署（DGX）

```bash
# 在 DGX 上，使用對應 aarch64/CUDA 的環境
pip install -r services/tts/requirements.txt
# 模型就緒後可用 TTS_MODEL_ID 覆寫模型 id
uvicorn services.tts.server:app --host 0.0.0.0 --port 8002
```

## 接到應用層

模型就緒後，於應用層 `.env` 設定（**對應的 `TTS_BACKEND`／`TTS_ENDPOINT` 設定與 `DgxTtsClient` 待加入應用層**）：

```dotenv
TTS_BACKEND=dgx
TTS_ENDPOINT=http://<dgx-host>:8002/synthesize
```

## 待辦（於 DGX 實機驗證）

- [ ] 選定／訓練台語 TTS 模型，鎖定載入方式與權重來源。
- [ ] 確認輸出音檔格式（取樣率、聲道、`wav`／`m4a`）與 LINE 可播放性。
- [ ] 鎖定 TTS 引擎在 aarch64 + CUDA 的版本。
- [ ] 加上逾時、併發與健康檢查（`/healthz`）。
- [ ] 應用層新增 `TTS_BACKEND`／`TTS_ENDPOINT` 設定與 `DgxTtsClient`，取代 `TextBubbleTts`。
