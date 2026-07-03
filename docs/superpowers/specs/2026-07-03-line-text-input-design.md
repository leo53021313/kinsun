# 設計：LINE 文字輸入（Debug 用打字進對話）

- 日期：2026-07-03
- 狀態：設計已核准，待實作
- 相關檔案：`src/kinsun/config.py`、`src/kinsun/pipeline.py`、`src/kinsun/channels/inbound.py`、`src/kinsun/channels/line/webhook.py`、`src/kinsun/app.py`、`.env.example`

## 背景與目的

目前 LINE 使用者只能用**語音**跟金孫對話：入站音檔會走
`VoicePipeline.process()`（ASR 轉文字 → 風險偵測 → agent → TTS → 回語音）。
自由文字（非綁定指令）目前會被 `dispatch` 導向綁定流程；`BindingFlow.handle`
對非綁定文字回 `None`，最後一律回覆「金孫現在聽得懂語音喔…」提示，**進不到 agent**。

需求：讓開發者能用**打字**觸發同一條對話管線，方便 Debug（不必每次錄音、
不依賴 ASR）。此為 Debug 輔助，正式上線行為維持不變。

## 決策（已與需求方確認）

1. **開放範圍**：以環境變數當 Debug 開關，**預設關閉**；開啟後才允許打字進對話。
   正式上線維持只收語音。
2. **回覆形式**：文字輸入也走 TTS、**回語音（附文字）**，與語音體驗一致；
   TTS／上傳失敗時沿用既有機制自動退回文字泡泡。
3. **綁定/consent 檢查**：文字路徑沿用與語音**相同的 `gate`**（風險偵測與家屬
   通知都需要「已綁定的長者」情境）。Debug 若要完全放行，另以既有旗標
   `BINDING_GATE_ENABLED=false` 搭配。
4. **綁定指令優先**：文字仍先進 `binding.handle`；只有回 `None` 的自由文字才轉進 agent。
5. **風險偵測照跑**：打字若含危急字句，一樣落庫＋通知家屬（與語音同一套 `detector.assess`）。

## 方案取捨

- **A（採用）** 管線抽出「ASR 之後」的共用核心，新增 `process_text()`；`dispatch`
  加旗標分支，文字回覆完全複用語音的 `voice.deliver`。改動小、語音／文字行為一致、
  風險偵測與觀測埋點自動沿用、無重複邏輯。
- **B（否決）** 只改 `dispatch`，文字直接呼叫 `agent.handle`：會繞過風險偵測＋家屬
  通知、繞過 TTS、觀測缺一段，且與「回語音」不符。
- **C（否決）** 另建獨立 `TextPipeline`：風險／生成／合成／觀測整套需複製，兩套並存
  難維護，過度設計。

## 詳細設計

### 1. 設定（`config.py` + `.env.example`）

- `Settings` 新增欄位 `line_text_input_enabled: bool`。
- `load_settings`：`line_text_input_enabled=_parse_bool(env.get("LINE_TEXT_INPUT_ENABLED", "false"))`
  （沿用 `binding_gate_enabled` 的寫法與命名慣例：欄位名＝環境變數鍵小寫、掛 `LINE_` 前綴）。
- `.env.example` 新增：
  ```
  LINE_TEXT_INPUT_ENABLED=false  # Debug 用：允許以打字進入對話（預設關，正式維持只收語音）
  ```

### 2. 管線（`pipeline.py`）

抽出「ASR 之後」的共用核心，讓語音與文字共用：

- 新增私有 `_process_transcribed(self, user_text, *, line_user_id, trace_id) -> TtsResult`，
  內容＝現行 `process()` 第 62–74 行（`assess` → L2+ 落庫/通知 → `_generate` → `_synthesize`
  → `replace(result, transcript=user_text)`）。
- `process()`（語音，維持既有簽章與行為）改為：
  ```python
  user_text = self._transcribe(audio, content_type=content_type,
                               line_user_id=line_user_id, trace_id=trace_id, audio_url=audio_url)
  return self._process_transcribed(user_text, line_user_id=line_user_id, trace_id=trace_id)
  ```
- 新增 `process_text(self, text, *, line_user_id, trace_id="") -> TtsResult`：
  直接 `return self._process_transcribed(text, line_user_id=line_user_id, trace_id=trace_id)`，
  **不呼叫 ASR**。`transcript` 欄位沿用共用核心設為輸入文字（與語音一致；
  `ASR_DEBUG_SHOW_TRANSCRIPT=true` 時 debug 泡泡的「辨識：」會顯示所打的字）。

### 3. 分派（`inbound.py`）

- `dispatch(...)` 新增參數 `text_input_enabled: bool = False`。
- text 分支改寫（維持綁定指令優先）：
  ```python
  if msg.kind == "text":
      reply = binding.handle(msg.line_user_id, msg.text)
      if reply is not None:
          msg.reply(reply)
          return
      if not text_input_enabled:
          msg.reply(NON_AUDIO_PROMPT)
          return
      if not gate.allows(msg.line_user_id):
          msg.reply(BIND_FIRST_PROMPT)
          return
      _run_pipeline(
          msg,
          lambda: pipeline.process_text(msg.text, line_user_id=msg.line_user_id, trace_id=msg.trace_id),
          voice=voice, traces=traces, timer=timer,
      )
      return
  ```
- 抽出共用 helper `_run_pipeline(msg, produce, *, voice, traces, timer)`，把現行語音分支的
  「產生 result → `voice.deliver`／退文字 → `_record_reply` → 例外回退 `FALLBACK_PROMPT`」那段
  收斂為單一實作；語音分支改成傳入 `lambda: pipeline.process(msg.audio, …)`。
  例外攔截維持 `(ASRError, LLMError, MemoryError)`（文字路徑不會拋 `ASRError`，保留無害）。

### 4. 接線（`webhook.py` + `app.py`）

- `_handle_events(...)` 與 `create_app(...)` 新增 `text_input_enabled: bool = False`，往下傳給 `dispatch`。
- `app.py` 的 `create_app(...)` 呼叫新增 `text_input_enabled=settings.line_text_input_enabled`。

## 資料流

```
LINE webhook → LineChannel.inbound()（正規化）→ dispatch()
  ├─ kind == "text":
  │     binding.handle → 有回覆就送出、結束
  │     否則 text_input_enabled?
  │        否 → NON_AUDIO_PROMPT
  │        是 → gate.allows? 否 → BIND_FIRST_PROMPT
  │                         是 → pipeline.process_text(text)
  │                               → _process_transcribed（風險→agent→TTS）
  │                               → voice.deliver（語音，失敗退文字）
  └─ kind == "audio"（不變）:
        gate.allows → pipeline.process(audio)（ASR→_process_transcribed）→ voice.deliver
```

## 錯誤處理

- 管線例外（`ASRError`／`LLMError`／`MemoryError`）由 `_run_pipeline` 攔截 → `FALLBACK_PROMPT`，與語音一致。
- TTS／音檔上傳失敗 → `VoiceReplyDelivery` 既有機制自動退回文字泡泡，回覆不遺失。
- 危急事件落庫失敗不中斷對話（沿用 `VoicePipeline` 既有 `try/except`）。

## 測試計畫

- `pipeline`：`process_text` 有跑 `assess`／`_generate`／`_synthesize`、**不呼叫 ASR**；
  transcript＝輸入文字；L2+ 有落庫＋通知。
- `inbound`：
  - 旗標關 → 非綁定文字仍回 `NON_AUDIO_PROMPT`（既有測試不動）。
  - 旗標開＋gate 通過＋非綁定文字 → 走 `process_text` 並以 `voice.deliver` 回覆。
  - 旗標開＋綁定指令（如「設定」）→ 仍走 `binding`，不進 agent。
  - 旗標開＋gate 擋 → `BIND_FIRST_PROMPT`。
- `line_webhook`：`text_input_enabled` 有正確從 `create_app` 傳達到 `dispatch`（可加輕量煙霧測試）。
- 既有 `test_text_routes_to_binding`、`test_text_none_falls_back_to_prompt` 因旗標預設關而不受影響。

## 文件

- `.env.example` 新增變數（含中文註解與預設值）。
- 若其他文件（README／設定清單）有列環境變數，一併補上 `LINE_TEXT_INPUT_ENABLED`。

## 非目標（Out of Scope）

- 不改語音既有行為與簽章。
- 不新增「文字輸入時改回文字」的選項（本次固定回語音；未來若需要另議）。
- 不處理圖片／貼圖等其他訊息型別（維持 `NON_AUDIO_PROMPT`）。
