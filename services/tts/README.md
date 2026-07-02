# TTS 服務（CosyVoice 3）— DGX 端

文字轉語音（繁體國語漢字 → 語音）推論服務。**僅在 DGX Spark 執行**（需 GPU 與 `cosyvoice`／`torch`），不屬於應用層、不進開發機的測試套件。

> 狀態：**已於 DGX 實機驗證**（2026-07-02，GB10 / aarch64 / CUDA 13）。CosyVoice 3 zero-shot
> 合成、wav→m4a、healthz、併發控制、`X-Duration-Ms` 皆通過；單句 RTF≈0.7（快於即時），
> 輸出 m4a 經 `ffprobe` 確認為 AAC/24kHz/單聲道且時長與標頭一致。
> 目前為**國語**語音；台語版本待後續只換本服務的合成實作，契約不變、應用層不動。
> 參考語音（金孫聲音）尚待正式定調——驗證時暫用 CosyVoice 內附 `asset/zero_shot_prompt.wav`。

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

CosyVoice 3 非 pip 套件：需 clone [FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) repo
（含 `cosyvoice/` 套件與 `third_party/Matcha-TTS`），並把模型權重放本機目錄。服務啟動時會把
`TTS_COSY_DIR` 與 `TTS_MATCHA_DIR` 加入 `sys.path`，並以 `AutoModel` 依模型目錄自動判別為 CosyVoice3。

```bash
# 在 DGX 的 cosyvoice 環境（含 torch/torchaudio/soundfile 與 CosyVoice repo 依賴）
pip install -r services/tts/requirements.txt   # fastapi/uvicorn/soundfile；torch 等依 CosyVoice repo
export TTS_MODEL_ID=/abs/path/to/Fun-CosyVoice3-0.5B-2512   # 本機權重目錄
export TTS_COSY_DIR=/abs/path/to/CosyVoice                  # CosyVoice repo
export TTS_PROMPT_WAV=/abs/path/to/prompt.wav               # 金孫參考語音
export TTS_PROMPT_TEXT='參考語音的逐字稿'
export TTS_PRELOAD=1
uvicorn services.tts.server:app --host 0.0.0.0 --port 8002
```

**系統需求：** `ffmpeg`（DGX 端把模型輸出的 wav 轉成 m4a／AAC，應用層跨平台不裝 ffmpeg）。
mp4/m4a 的 `moov` atom 需可 seek 的輸出，故服務走可 seek 的暫存檔轉檔再讀回（非 `pipe`）。

**aarch64 注意：** torchaudio 的 load/save 會走 torchcodec（`.so` 載不起來），服務以 `soundfile`
取代之。zero-shot 逐字稿內部會加 instruct 前綴 `You are a helpful assistant.<|endofprompt|>`，
否則 LLM 會立刻 EOS、產不出語音。

**環境變數：**

| 環境變數 | 預設 | 用途 |
|---|---|---|
| `TTS_MODEL_ID` | `FunAudioLLM/Fun-CosyVoice3-0.5B-2512` | 模型 id 或本機權重目錄（本機優先，免下載） |
| `TTS_COSY_DIR` | 空（必填） | CosyVoice repo 目錄（加入 `sys.path`），缺會載入時明確報錯 |
| `TTS_MATCHA_DIR` | 空 | Matcha-TTS 目錄，留空＝`{TTS_COSY_DIR}/third_party/Matcha-TTS` |
| `TTS_PROMPT_WAV` | 空（必填） | 參考音檔路徑（金孫聲音，5–15 秒乾淨人聲），缺會啟動時明確報錯 |
| `TTS_PROMPT_TEXT` | 空（必填） | `TTS_PROMPT_WAV` 的逐字稿 |
| `TTS_MAX_CONCURRENCY` | `1` | 同時處理的合成請求數（threadpool + semaphore） |
| `TTS_MAX_QUEUE` | `8` | 等候佇列上限，超過回 503 |
| `TTS_PRELOAD` | `0` | 設 `1` 於服務啟動（lifespan）即載入模型，預設延遲載入（大小寫不敏感） |

## 接到應用層

於應用層 `.env` 設定：

```dotenv
TTS_BACKEND=dgx
TTS_ENDPOINT=http://<dgx-host>:8002/synthesize
```

`TTS_BACKEND=dgx` 時 `build_tts_client` 會建立 `DgxTtsClient`；缺 `TTS_ENDPOINT` 會在組裝期報錯。
語音回覆另需設定音檔發佈（`SUPABASE_URL`／`SUPABASE_SERVICE_KEY`／`AUDIO_BUCKET`，見專案根 [README.md](../../README.md)）。

## 待辦（於 DGX 實機驗證）

- [x] 選定 TTS 模型：**CosyVoice 3**（`FunAudioLLM/Fun-CosyVoice3-0.5B-2512`），已實作並實機驗證 zero-shot 合成。
      台語版本待後續替換 `server.py` 的合成實作（契約不變）。
- [x] 在 aarch64 + CUDA 上實際裝起 CosyVoice 3 並跑通（torch 2.12.1+cu130、`AutoModel`、`soundfile` 取代 torchaudio、instruct 前綴）。
- [x] 併發與健康檢查（`GET /healthz`）——threadpool + semaphore + 佇列上限 503。
- [x] 應用層新增 `TTS_BACKEND`／`TTS_ENDPOINT` 設定與 `DgxTtsClient`，取代 `TextBubbleTts`——已實作（`build_tts_client`）。
- [x] wav→m4a 轉檔（可 seek 暫存檔）並經 `ffprobe` 確認為合法 m4a；`X-Duration-Ms` 與實際時長一致。
- [ ] 錄製並定調正式**金孫參考語音**（目前驗證暫用 CosyVoice 內附範例聲）。
- [ ] 以真 LINE 帳號驗 `AudioMessage` 播放（需部署 app + 公開 URL；模型端 m4a 已確認可播）。
- [ ] 服務端逐請求 timeout（目前僅呼叫端 `DgxTtsClient` 有 urlopen 逾時；模型卡住會佔住 semaphore 槽位）。
