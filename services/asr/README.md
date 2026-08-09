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
| 解碼失敗 | 音檔無法解碼（ffmpeg 失敗或 0 樣本）→ 回 422（`audio_decode_failed`），ffmpeg stderr 記入服務 log 供查根因 |
| 純靜音 | 峰值低於 `ASR_SILENCE_PEAK` → 直接回 `{"text": ""}`、不進模型（Whisper 對靜音會幻覺出重複語句） |
| 辨識語言 | 由 `ASR_LANGUAGE`（預設 `zh`）**釘死**，不做自動偵測——語言槽留空會讓近無聲音檔的偵測結果變成垃圾、解碼跑進重複迴圈（見下方「為什麼一定要釘語言」） |
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
| `ASR_MAX_QUEUE` | `8` | 等候佇列上限，超過回 503（`overloaded`） |
| `ASR_API_KEY` | 空 | 共用金鑰（✅ D-56）：設定後驗 `X-Api-Key`（錯誤回 401）；留空＝內網不驗 |
| `ASR_MAX_BODY_BYTES` | `10485760` | 單請求 body 上限（bytes）；超過回 413、空 body 回 400（✅ D-26） |
| `ASR_PRELOAD` | `0` | 設 `1` 於服務啟動（lifespan）即載入模型。⚠️ **`scripts/kinsun.sh` 啟動時一律帶 `1`**（2026-08-07 起，見 docs/dev/14 §1「GPU 模型預熱」）——預設 0 是給沒有 GPU 的開發機用的，正式機延遲載入等於讓長輩的第一句話去撞 CUDA OOM |
| `ASR_SILENCE_PEAK` | `0.001` | 靜音峰值閘（約 -60 dBFS）：解碼後峰值低於此值視為純靜音，回空字串不進模型（2026-07-18 實錄：0.35 秒空錄音讓模型幻覺「來，請坐…」迴圈、一輪空燒約 10 秒 GPU） |
| `ASR_LANGUAGE` | `zh` | **釘死辨識語言**（V-01，2026-07-29）。空字串＝回到自動偵測（修正前行為），是就地回退的逃生口。詳見下方「為什麼一定要釘語言」 |

> DGX Spark（GB10）實機驗證：不指定 device 會落在 CPU、一句數十秒；GPU + fp16 才夠即時（真人聲實測約 1.1 秒）。
> `server.py` 已依此鎖定 `device=0`／`torch.float16`（無 GPU 時退回 CPU／fp32，供開發機無 GPU 情境使用）。
> 2026-07-02 端到端實機：把 CosyVoice 3 合成的 m4a 餵入本服務，辨識回近乎一致的文字
> （torch 2.12.1+cu130、transformers 5.x）。

## 為什麼一定要釘語言（V-01，2026-07-29）

模型的 `generation_config` 是：

```
forced_decoder_ids = [[1, None], [2, 50359]]
                          ↑            ↑
                    語言槽＝None   <|transcribe|>
```

**任務釘住了，語言沒釘。** 語言槽是 `None`＝未指定，所以每一次請求都先跑一次**自動語言偵測**。音檔清楚時偵測得準；近無聲、或句尾帶一小段靜音時偵測結果是垃圾，解碼隨即跑進退化迴圈。

**實測（同檔各跑 6 次，真模型）**

| 音檔 | 不釘語言 | 釘 `zh` |
| :--- | :--- | :--- |
| 0.76 秒「早安」 | **「晴文」×60（6/6）** | 「早安」（0/6） |
| 同一句截到 0.68 秒 | 「早安」 | 「早安」 |
| 白噪音 | 「Jaa」 | 「來」 |
| 極輕白噪音 | **「Vytautas」**（立陶宛人名） | 「來」 |
| 「好好好對對對我知道了」 | 正確 | 正確 |
| 「你的 blood pressure 有量嗎」 | `Blood Pressure` | **「血壓」** |

三件要記住的事：

1. **觸發點是句尾那一小段靜音，不是音檔短。** 同一句截短反而正常——照「音檔太短」去寫防護會防錯地方。
2. **噪音被辨識成外語**（立陶宛人名）而非亂碼，正是「語言偵測選錯」的指紋。釘 `zh` 後收斂成中文短字。
3. **副作用已實測、判定可接受**：`blood pressure` 這類常見英文詞會被寫成「血壓」而非保留原文（專有名詞如 YouTube 仍保留）。對本產品反而更好——危急關鍵詞表與 LLM 都吃中文。

那串幻覺文字會進危急分級器，實錄曾因此**真的送出假警報給家屬**（`risk_notification_logs` 的 `outcome=sent, delivered=true`）。

⚠️ **不要改用 `num_beams=1`**：實測它也能消除幻覺，但它在模型設定裡本來就是預設值卻仍改變行為，機制不明。不明機制的修法升 `transformers` 版本就可能失效，而且失效時沒有任何測試會紅——只有家屬開始收到假警報。

⚠️ **仍有一塊修不掉**：任何設定下，雜音都還是會吐出某些字（釘 `zh` 後是「來」）。那些字會進分級器與長期記憶，故應用層 `pipeline.py` 仍需一道輸出端守門，或在 ASR 之前加 VAD。

⚠️ **本次樣本是 TTS 合成語音**，不含口音與環境噪音。上線後應以真實長輩錄音回歸一次。

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
