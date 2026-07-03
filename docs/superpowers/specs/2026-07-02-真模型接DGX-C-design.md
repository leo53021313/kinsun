# 真模型接 DGX 設計（C 切片：真 ASR 硬化＋真 TTS 全鏈路）

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：③ 語音層（ASR/TTS）、① LINE 通道。
> 前置：ASR 服務已於 DGX 實機驗證 GPU 推論（commit `fe9e336`）；`DgxAsrClient` 與 `ASR_BACKEND` 開關已存在。
> 本案把「真模型接 DGX」做完：ASR 完整硬化＋TTS 從模型服務到 LINE 語音回覆的整條鏈路。

---

## 1. 背景與目標

目前 ASR 已可呼叫 DGX 真模型，但服務端有阻塞 event loop 的問題、無健康檢查與併發控制；
TTS 仍是文字泡泡 placeholder（`TextBubbleTts`），`services/tts` 只有骨架、模型未選定，
LINE 回覆路徑也只支援文字。

**完成後：** 長輩傳 LINE 語音 → DGX 真 ASR（Breeze-ASR-26）辨識 → 回覆經 DGX 真 TTS
（CosyVoice 3）合成 → 以 **LINE 語音訊息＋文字泡泡**回覆（可設定只發語音）；
任何一段（TTS、上傳、LINE 語音）失敗都退化成純文字，對話不中斷。

**端到端資料流：**

```
LINE 語音 → webhook → VoicePipeline
  ├─ ASR：DgxAsrClient ──POST bytes──→ DGX services/asr（硬化：healthz/併發/預載）
  ├─ 危急偵測 + CareAgent（不動）
  └─ TTS：DgxTtsClient ──POST {"text"}──→ DGX services/tts（CosyVoice 3）
                                             └→ 回 m4a bytes + X-Duration-Ms
dispatch 收到 TtsResult(audio 有值)
  → SupabaseAudioPublisher 上傳 → 公開 HTTPS URL
  → messenger.reply_voice(reply_token, url, duration_ms, 文字?)
     └→ LINE AudioMessage（＋TextMessage，依 TTS_REPLY_TEXT）
```

---

## 2. 範圍（Scope）

### 2.1 在範圍內

* `services/tts/`：CosyVoice 3 載入與合成、wav→m4a 轉檔與時長計算、healthz/併發/預載、requirements 鎖版。
* `services/asr/`：threadpool＋semaphore 修阻塞、healthz、預載、佇列上限 503、requirements 鎖版。
* `src/kinsun/speech/tts.py`：`TtsResult.duration_ms`、`TTSError`、`DgxTtsClient`、`build_tts_client`。
* `src/kinsun/audio/publisher.py`（新套件）：`AudioPublisher` Protocol、`SupabaseAudioPublisher`、`AudioPublishError`、`build_audio_publisher`。
* `src/kinsun/channels/`：`LineMessenger.reply_voice`、`InboundMessage.reply_voice`、`VoiceReplyDelivery`、`dispatch` 接線。
* `src/kinsun/pipeline.py`：TTS fail-safe（`TTSError` → 純文字結果）。
* `src/kinsun/config.py`、`app.py`、`scheduler/worker.py`：新設定、組裝、音檔清理每日 job。
* 文件：兩個 services README、專案 README 環境變數、progress.md。

### 2.2 不在範圍內（後續）

* 台語 TTS 模型（本案接國語 CosyVoice 3；台語模型就緒後只換 `services/tts` 的合成實作，契約不變）。
* ASR/TTS 服務的多實例、負載平衡、認證（服務僅在內網供 app 呼叫）。
* 語音訊息的已讀/播放回執、串流合成。

---

## 3. DGX TTS 服務（services/tts/server.py）

### 3.1 模型與參考語音

* 模型：`FunAudioLLM/Fun-CosyVoice3-0.5B-2512`，以 `TTS_MODEL_ID` 覆寫。
* zero-shot 聲音複製：金孫聲音由兩個環境變數決定，服務啟動時檢查、缺就明確報錯——
  * `TTS_PROMPT_WAV`：參考音檔路徑（5–15 秒、乾淨人聲）。
  * `TTS_PROMPT_TEXT`：該音檔的逐字稿。
* 載入 API 以 [FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) repo 為準，
  於 DGX 實機驗證時鎖定寫法與版本（見 §11 清單第 1 項）。

### 3.2 契約（更新既有 README 的契約表）

| 項目 | 內容 |
|------|------|
| 路徑 | `POST /synthesize` |
| 請求 | JSON `{"text": "<繁體國語漢字>"}` |
| 回應 | body 為 **m4a（AAC）bytes**、`Content-Type: audio/mp4`、header `X-Duration-Ms: <int>` |
| 健康檢查 | `GET /healthz` → `{"status": "ok", "model_loaded": <bool>}` |
| 過載 | 佇列滿回 503 |

* 轉檔放 DGX 端（ffmpeg：wav → AAC/m4a），因為應用層要在 Windows/macOS 跑、不能要求裝 ffmpeg。
* 時長由模型輸出波形算（樣本數 ÷ 取樣率），不需 ffprobe。

### 3.3 併發與載入

* 推論丟 threadpool（不卡 event loop）＋ semaphore 序列化：`TTS_MAX_CONCURRENCY` 預設 1。
* 等候中請求超過 `TTS_MAX_QUEUE`（預設 8）→ 503。
* `TTS_PRELOAD=1` 於 lifespan 啟動即載入模型（預設 0 維持延遲載入）。

---

## 4. DGX ASR 服務硬化（services/asr/server.py）

* **修 bug**：現行 `async def transcribe` 直接跑阻塞推論會卡死 event loop → 改
  threadpool＋semaphore，與 §3.3 同款（`ASR_MAX_CONCURRENCY` 預設 1、`ASR_MAX_QUEUE` 預設 8、超載 503）。
* 加 `GET /healthz`（同 §3.2 格式）與 `ASR_PRELOAD`（預設 0）。
* 應用層不用改：`DgxAsrClient` 已把 HTTP 錯誤轉 `ASRError` → dispatch 回「沒聽清楚」提示。
* requirements：以 DGX（aarch64＋CUDA）實測版本鎖定；README 補系統需求 **ffmpeg**
  （HF pipeline 解 m4a 依賴）。

---

## 5. 應用層 TTS client（speech/tts.py）

```python
@dataclass(frozen=True)
class TtsResult:
    text: str
    audio: bytes | None = None
    duration_ms: int = 0          # 新增：audio 有值時有效

class TTSError(Exception): ...    # 新增

class DgxTtsClient:               # 新增：與 DgxAsrClient 同款式（標準庫 urllib，零新依賴）
    def __init__(self, endpoint: str, timeout: float) -> None: ...
    def synthesize(self, text: str) -> TtsResult:
        # POST JSON {"text"} → m4a bytes + X-Duration-Ms header
        # 網路/HTTP/回應缺 header → TTSError

def build_tts_client(settings: Settings) -> TTSClient:
    # TTS_BACKEND=dgx → DgxTtsClient（缺 TTS_ENDPOINT → TTSError）
    # 其他 → TextBubbleTts()
```

`VoicePipeline.process` 加 fail-safe：`self._tts.synthesize(reply_text)` 拋 `TTSError` 時
log 後回 `TtsResult(text=reply_text, audio=None)`——回覆文字絕不因 TTS 掛掉而消失。

---

## 6. 音檔發佈（audio/publisher.py，新套件）

```python
class AudioPublishError(Exception): ...

class AudioPublisher(Protocol):
    def publish(self, audio: bytes, *, content_type: str) -> str: ...   # 回公開 URL

class SupabaseAudioPublisher:
    """Supabase Storage REST API（標準庫 urllib、service key 走環境變數，不加 SDK）。"""
    def __init__(self, base_url: str, service_key: str, bucket: str,
                 *, timeout: float, clock, new_id) -> None: ...
    # 上傳：POST {base}/storage/v1/object/{bucket}/tts/{yyyymmdd}/{uuid}.m4a
    # 回傳：{base}/storage/v1/object/public/{bucket}/tts/{yyyymmdd}/{uuid}.m4a

def build_audio_publisher(settings: Settings, *, clock, new_id) -> AudioPublisher:
    # 缺 SUPABASE_URL / SUPABASE_SERVICE_KEY → AudioPublishError
```

* 路徑帶日期資料夾 `tts/{yyyymmdd}/`，清理只要刪整個過期資料夾。
* `clock`／`new_id` 注入（沿用專案 TDD 慣例）。
* bucket 為**公開 bucket**（預設 `tts-audio`），需在 Supabase 後台手動建立一次，步驟寫進 README。
* 清理：`scheduler/worker.py` 加每日 job（沿用既有 `Scheduler`），刪除超過
  `AUDIO_RETENTION_DAYS`（預設 2 天）的日期資料夾；失敗只 log、不影響其他 job（錯誤隔離已內建）。

---

## 7. LINE 語音回覆（channels/）

### 7.1 messenger.py

* `LineMessenger` Protocol 增：
  `reply_voice(reply_token: str, audio_url: str, duration_ms: int, text: str | None) -> None`。
* `LineApiMessenger` 實作：一次 `reply_message` 發
  `[AudioMessage(originalContentUrl=url, duration=ms)]`，`text` 非 None 時再附 `TextMessage`。

### 7.2 inbound.py 與 channel.py

* `InboundMessage` 增欄位 `reply_voice: Callable[[str, int, str | None], None]`
  （url、duration_ms、text；由 `LineChannel` 綁定 reply_token）。
  一個 reply_token 只能用一次，`reply` 與 `reply_voice` 二擇一，由 dispatch 保證。
* 新增小物件 `VoiceReplyDelivery`（放 inbound.py）：

```python
class VoiceReplyDelivery:
    def __init__(self, publisher: AudioPublisher | None, include_text: bool) -> None: ...
    def deliver(self, msg: InboundMessage, result: TtsResult) -> None:
        # audio 為 None（文字泡泡模式或 TTS 已退化）或 publisher 為 None（防禦）
        #   → msg.reply(result.text)
        # 有 audio → publish → msg.reply_voice(url, duration_ms, text if include_text else None)
        # publish 或 reply_voice 失敗 → 退回 msg.reply(result.text)
```

* 退化為盡力而為：若 `reply_voice` 失敗時 reply_token 已被消耗，補發的 `msg.reply`
  會再失敗——由 webhook 既有的事件層 catch 記錄，不會回 500（LINE 不會重送整包事件）。

* `dispatch(msg, *, pipeline, binding, gate, voice)`：語音訊息處理成功後改呼叫
  `voice.deliver(msg, result)`（原本是 `msg.reply(result.text)`）。

---

## 8. 設定與接線（config.py、app.py、worker.py）

| 環境變數 | 預設 | 用途 |
|---|---|---|
| `TTS_BACKEND` | `bubble` | `dgx` 啟用真 TTS |
| `TTS_ENDPOINT` | 空（dgx 時必填） | DGX TTS 服務位址 |
| `TTS_TIMEOUT_SECONDS` | `30` | 合成逾時 |
| `TTS_REPLY_TEXT` | `true` | `true`＝語音＋文字；`false`＝只語音 |
| `SUPABASE_URL` | 空（dgx 時必填） | Storage REST 基底 |
| `SUPABASE_SERVICE_KEY` | 空（dgx 時必填） | Storage 上傳金鑰 |
| `AUDIO_BUCKET` | `tts-audio` | 公開 bucket 名稱 |
| `AUDIO_RETENTION_DAYS` | `2` | 音檔保留天數（清理 job） |
| `AUDIO_UPLOAD_TIMEOUT_SECONDS` | `10` | 上傳逾時 |

* `Settings` 增對應欄位；`TTS_BACKEND=dgx` 而缺必填時，於組裝期就報錯
  （`build_tts_client` → `TTSError`、`build_audio_publisher` → `AudioPublishError`），訊息指名缺哪個變數。
* `app.build_app`：`tts=build_tts_client(settings)`；`TTS_BACKEND=dgx` 時建 publisher，
  否則 publisher 為 None；`VoiceReplyDelivery(publisher, settings.tts_reply_text)` 傳進 `create_app` → dispatch。
* `scheduler/worker.py`：`TTS_BACKEND=dgx` 時註冊音檔清理每日 job。
* DGX 服務端環境變數（`TTS_MODEL_ID`、`TTS_PROMPT_WAV`、`TTS_PROMPT_TEXT`、`*_MAX_CONCURRENCY`、
  `*_MAX_QUEUE`、`*_PRELOAD`）記載於各自 README，不進應用層 `Settings`。

---

## 9. 測試策略

* **單元測試（離線 fake、進 CI，沿用注入式風格）：**
  * `DgxTtsClient`：成功、HTTP 錯誤、缺 `X-Duration-Ms`、逾時 → `TTSError`。
  * `build_tts_client`：開關與缺設定。
  * `SupabaseAudioPublisher`：假傳輸驗 URL/路徑/標頭；錯誤 → `AudioPublishError`。
  * `VoiceReplyDelivery`：無音檔→文字、有音檔→語音（含/不含文字）、publish 失敗→退化文字。
  * `VoicePipeline`：TTS 拋錯 → 回純文字結果（既有危急/回覆行為不變）。
  * `LineChannel`：`reply_voice` 綁定 reply_token。
  * config：新欄位預設與解析。
  * 既有測試同步補 `InboundMessage.reply_voice` 欄位與 fakes。
* **services 不進開發機測試套件**（既有原則）；服務端行為以 §11 實機清單驗證。

---

## 10. 錯誤處理（fail-safe 總表）

| 失敗點 | 行為 |
|---|---|
| ASR 服務掛/超載/逾時 | `ASRError` → 「金孫剛剛沒聽清楚…」（既有） |
| TTS 服務掛/超載/逾時 | `TTSError` → pipeline 退化純文字結果 |
| Supabase 上傳失敗 | `AudioPublishError` → `VoiceReplyDelivery` 退回文字泡泡 |
| LINE 語音回覆失敗 | `VoiceReplyDelivery` 捕捉 → 改發文字泡泡 |
| 音檔清理 job 失敗 | 只 log，不影響其他排程（Scheduler 既有錯誤隔離） |

危急通知在回覆生成之前（既有設計），不受 TTS/上傳任何失敗影響。

---

## 11. DGX 實機驗證清單（實作時逐項打勾）與風險

1. [ ] **CosyVoice 3 在 aarch64＋CUDA 裝得起來**——最大風險，排第一步先驗：
   `ttsfrd` 只有 x86 wheel，需退 WeTextProcessing（pynini 在 ARM 可能要編譯）；
   裝不起來回頭議備案（BreezyVoice／其他引擎），契約不變。
2. [ ] 參考語音錄製與試聽（金孫聲音定調），單句合成延遲與音質可接受。
3. [ ] wav→m4a 轉檔後 LINE 實機可播放（AudioMessage）。
4. [ ] ASR/TTS 併發行為：同時多請求不卡死、超載回 503、app 端正確退化。
5. [ ] 端到端：LINE 語音進 → 真 ASR → 真 TTS → LINE 語音出，延遲壓在 reply token 有效期內。
6. [ ] requirements 版本鎖定（torch/transformers/CosyVoice 依賴）。

---

## 12. 已定決策（列出供否決）

1. TTS 模型用 **CosyVoice 3**（使用者指定；台語模型後續換 `services/tts` 實作即可）。
2. 音檔託管走 **Supabase Storage 公開 bucket**（使用者指定），不走 app 自託管。
3. wav→m4a 轉檔與時長計算在 **DGX 服務端**（應用層跨平台、不裝 ffmpeg）。
4. 回覆形式 `TTS_REPLY_TEXT` 切換，**預設語音＋文字**；TTS 任何失敗退化純文字。
5. 應用層 HTTP 一律 **標準庫 urllib**（與 `DgxAsrClient` 一致），不加 supabase SDK／httpx 依賴。
6. 音檔以日期資料夾存放、每日排程清理（預設保留 2 天）。
7. services/ 維持不進開發機測試套件；服務端以實機清單驗證。
