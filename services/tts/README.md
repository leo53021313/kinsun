# TTS 服務（CosyVoice 3）— DGX 端

文字轉語音（繁體國語漢字 → 語音）推論服務。**僅在 DGX Spark 執行**（需 GPU 與 `cosyvoice`／`torch`），不屬於應用層、不進開發機的測試套件。

> 狀態：**程式碼已實作**（CosyVoice 3 zero-shot 聲音複製、wav→m4a 轉檔、healthz、併發控制），
> 但**尚未於 DGX 實機驗證**（安裝、GPU 推論、參考語音效果、LINE 播放）。
> 目前為**國語**語音；台語版本待後續只換本服務的合成實作，契約不變、應用層不動。

## 與應用層的契約

| 項目 | 內容 |
|------|------|
| 路徑 | `POST /synthesize` |
| 請求 | JSON `{"text": "<繁體國語漢字>"}` |
| 回應 | body 為 **m4a（AAC）bytes**、`Content-Type: audio/mp4`、header `X-Duration-Ms: <int>`（合成語音毫秒數） |
| 健康檢查 | `GET /healthz` → `{"status": "ok", "model_loaded": <bool>}` |
| 過載 | 等候請求數超過 `TTS_MAX_CONCURRENCY + TTS_MAX_QUEUE` → 回 503 |
| 呼叫端 | `kinsun.speech.tts.DgxTtsClient`（已實作，見 [tts.py](../../src/kinsun/speech/tts.py)） |

> `DgxTtsClient` 會把回應包成 `TtsResult(text=text, audio=<bytes>, duration_ms=<int>)`，
> 介面與既有 `TTSClient.synthesize(text) -> TtsResult` 一致。

## 部署（DGX）

```bash
# 在 DGX 上，使用對應 aarch64/CUDA 的環境
pip install -r services/tts/requirements.txt
uvicorn services.tts.server:app --host 0.0.0.0 --port 8002
```

**系統需求：** `ffmpeg`（DGX 端把模型輸出的 wav 轉成 m4a／AAC，應用層跨平台不裝 ffmpeg）。

**環境變數：**

| 環境變數 | 預設 | 用途 |
|---|---|---|
| `TTS_MODEL_ID` | `FunAudioLLM/Fun-CosyVoice3-0.5B-2512` | 覆寫模型 id |
| `TTS_PROMPT_WAV` | 空（必填） | 參考音檔路徑（金孫聲音，5–15 秒乾淨人聲），缺會啟動時明確報錯 |
| `TTS_PROMPT_TEXT` | 空（必填） | `TTS_PROMPT_WAV` 的逐字稿 |
| `TTS_MAX_CONCURRENCY` | `1` | 同時處理的合成請求數（threadpool + semaphore） |
| `TTS_MAX_QUEUE` | `8` | 等候佇列上限，超過回 503 |
| `TTS_PRELOAD` | `0` | 設 `1` 於服務啟動（lifespan）即載入模型，預設延遲載入 |

## 接到應用層

於應用層 `.env` 設定：

```dotenv
TTS_BACKEND=dgx
TTS_ENDPOINT=http://<dgx-host>:8002/synthesize
```

`TTS_BACKEND=dgx` 時 `build_tts_client` 會建立 `DgxTtsClient`；缺 `TTS_ENDPOINT` 會在組裝期報錯。
語音回覆另需設定音檔發佈（`SUPABASE_URL`／`SUPABASE_SERVICE_KEY`／`AUDIO_BUCKET`，見專案根 [README.md](../../README.md)）。

## 待辦（於 DGX 實機驗證）

- [x] 選定 TTS 模型：**CosyVoice 3**（`FunAudioLLM/Fun-CosyVoice3-0.5B-2512`），已實作 zero-shot 聲音複製合成。
      台語版本待後續替換 `server.py` 的合成實作（契約不變）。
- [ ] 在 aarch64 + CUDA 上實際裝起 CosyVoice 3（`ttsfrd` 僅 x86 wheel，需退 `WeTextProcessing`，`pynini` 於 ARM 可能要編譯）；裝不起來須回頭議備案引擎。
- [ ] 錄製並試聽參考語音（金孫聲音定調），確認單句合成延遲與音質可接受。
- [ ] 確認 wav→m4a 轉檔後 LINE 實機可播放（`AudioMessage`）。
- [x] 加上逾時、併發與健康檢查（`GET /healthz`）——已於程式碼實作（threadpool + semaphore + 佇列上限 503）。
- [x] 應用層新增 `TTS_BACKEND`／`TTS_ENDPOINT` 設定與 `DgxTtsClient`，取代 `TextBubbleTts`——已實作（`build_tts_client`）。
- [ ] `requirements.txt` 依 DGX 實機驗證結果鎖定版本（torch/torchaudio/CosyVoice 依賴）。
