# LINE 文字輸入（Debug 用打字進對話）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在環境變數旗標開啟時，讓 LINE 使用者能以打字（非綁定自由文字）觸發與語音相同的對話管線，方便 Debug；預設關閉，正式維持只收語音。

**Architecture:** 於 `VoicePipeline` 抽出「ASR 之後」的共用核心 `_process_transcribed`，新增 `process_text()` 跳過 ASR 直接進核心；`dispatch` 加 `text_input_enabled` 旗標分支，文字回覆完全複用語音的 `voice.deliver`（TTS→語音，失敗退文字）。旗標由 `Settings.line_text_input_enabled` 一路接線到 `dispatch`。

**Tech Stack:** Python 3、FastAPI、pytest、線上 LINE Messaging API（linebot v3）。

**設計來源：** `docs/superpowers/specs/2026-07-03-line-text-input-design.md`

## Global Constraints

- 一律台灣繁體中文（文件、註解、commit 訊息）。
- OS-agnostic：走環境變數、不寫死路徑。
- 命名慣例：`Settings` 欄位名＝環境變數鍵小寫、一一對應；此旗標掛 `LINE_` 前綴（沿用 `binding_gate_enabled` 樣式）。布林設定用 `_parse_bool(env.get(KEY, "false"))`。
- 只在 `Leo` 分支工作，不 push、不改 Git 歷史。
- 不改語音既有行為與簽章；改動範圍盡量小。
- 程式讀取的每個環境變數鍵都必須列在 `.env.example`（附預設值＋一行中文註解）。
- 例外攔截型別維持 `(ASRError, LLMError, MemoryError)`。

---

### Task 1: 新增設定旗標 `line_text_input_enabled`

**Files:**
- Modify: `src/kinsun/config.py:36-80`（`Settings` 加欄位）、`src/kinsun/config.py:93-138`（`load_settings` 加解析）
- Modify: `.env.example:1-3`（LINE 區塊新增變數）
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.line_text_input_enabled: bool`（預設 `False`；環境變數鍵 `LINE_TEXT_INPUT_ENABLED`）。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_config.py` 尾端新增：

```python
def test_load_settings_line_text_input_default_false():
    assert load_settings(BASE_ENV).line_text_input_enabled is False


def test_load_settings_line_text_input_enabled_values():
    for raw in ("true", "1", "yes", "True"):
        s = load_settings({**BASE_ENV, "LINE_TEXT_INPUT_ENABLED": raw})
        assert s.line_text_input_enabled is True, raw


def test_load_settings_line_text_input_disabled_values():
    for raw in ("false", "0", "no", "False"):
        s = load_settings({**BASE_ENV, "LINE_TEXT_INPUT_ENABLED": raw})
        assert s.line_text_input_enabled is False, raw
```

並在既有 `test_load_settings_reads_required_and_defaults` 內（`assert settings.asr_debug_show_transcript is False` 之後）加一行：

```python
    assert settings.line_text_input_enabled is False
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL —`TypeError`（`Settings` 缺 `line_text_input_enabled`）或 `AttributeError`。

- [ ] **Step 3: 實作最小程式**

在 `src/kinsun/config.py` 的 `Settings` dataclass，於 `asr_debug_show_transcript: bool` 之後新增欄位：

```python
    line_text_input_enabled: bool
```

在 `load_settings(...)` 回傳的 `Settings(...)` 內，於 `asr_debug_show_transcript=...` 之後新增：

```python
        line_text_input_enabled=_parse_bool(env.get("LINE_TEXT_INPUT_ENABLED", "false")),
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS（全數通過）。

- [ ] **Step 5: 更新 `.env.example`**

在 `.env.example` 的 `LINE_CHANNEL_ACCESS_TOKEN=` 那一行之後（第 3 行後）插入：

```
# Debug 用：允許以打字（非綁定自由文字）進入對話管線；預設關，正式維持只收語音
LINE_TEXT_INPUT_ENABLED=false
```

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/config.py tests/test_config.py .env.example
git commit -m "feat: 新增 LINE_TEXT_INPUT_ENABLED 設定旗標"
```

---

### Task 2: `VoicePipeline` 抽共用核心並新增 `process_text`

**Files:**
- Modify: `src/kinsun/pipeline.py:46-74`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: 既有 `Settings` 無關；使用 `RiskTier`、`TtsResult`、`replace`。
- Produces:
  - `VoicePipeline.process_text(self, text: str, *, line_user_id: str, trace_id: str = "") -> TtsResult`（跳過 ASR，跑風險偵測→agent→TTS；`transcript` 設為輸入文字）。
  - 私有 `VoicePipeline._process_transcribed(self, user_text: str, *, line_user_id: str, trace_id: str) -> TtsResult`。
  - `process()` 行為與簽章不變。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_pipeline.py` 尾端新增（`_ExplodingAsr` 用來證明 `process_text` 不呼叫 ASR）：

```python
class _ExplodingAsr:
    def transcribe(self, audio, *, content_type):
        raise AssertionError("process_text 不應呼叫 ASR")


def _text_pipeline(detector, notifier, risk_events=None):
    return VoicePipeline(
        asr=_ExplodingAsr(),
        agent=CareAgent(EchoLLM(), NullMemory(), NullContext()),
        tts=TextBubbleTts(),
        detector=detector,
        notifier=notifier,
        risk_events=risk_events or FakeRiskEventStore(),
    )


def test_process_text_skips_asr_and_replies():
    notifier = SpyNotifier()
    result = _text_pipeline(StubDetector(RiskTier.L0), notifier).process_text(
        "我想聊天", line_user_id="u1"
    )
    assert result.text == "你說的是：我想聊天"
    assert result.transcript == "我想聊天"
    assert notifier.calls == []


def test_process_text_notifies_and_records_on_l3():
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    _text_pipeline(StubDetector(RiskTier.L3), notifier, events).process_text(
        "救命", line_user_id="u1", trace_id="t9"
    )
    assert notifier.calls == [("u1", RiskTier.L3)]
    assert events.recorded_trace_ids == ["t9"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_pipeline.py -k process_text -q`
Expected: FAIL —`AttributeError: 'VoicePipeline' object has no attribute 'process_text'`。

- [ ] **Step 3: 實作最小程式（抽核心 + 新方法）**

將 `src/kinsun/pipeline.py` 的 `process` 方法（第 46-74 行）整段替換為下列三個方法：

```python
    def process(
        self,
        audio: bytes,
        *,
        line_user_id: str,
        content_type: str = "audio/m4a",
        trace_id: str = "",
        audio_url: str = "",
    ) -> TtsResult:
        user_text = self._transcribe(
            audio,
            content_type=content_type,
            line_user_id=line_user_id,
            trace_id=trace_id,
            audio_url=audio_url,
        )
        return self._process_transcribed(user_text, line_user_id=line_user_id, trace_id=trace_id)

    def process_text(self, text: str, *, line_user_id: str, trace_id: str = "") -> TtsResult:
        """文字輸入路徑（Debug）：跳過 ASR，直接以輸入文字進入對話核心。"""
        return self._process_transcribed(text, line_user_id=line_user_id, trace_id=trace_id)

    def _process_transcribed(
        self, user_text: str, *, line_user_id: str, trace_id: str
    ) -> TtsResult:
        assessment = self._detector.assess(user_text)
        # 危急通知須獨立於回覆生成：先落庫＋通知家屬，才產生回覆。
        # 否則 agent 生成回覆時若丟例外，會讓已偵測到的危急漏通知。
        if assessment.tier >= RiskTier.L2:
            try:
                self._risk_events.record(line_user_id, assessment, trace_id=trace_id or None)
            except Exception:  # noqa: BLE001 - 落庫失敗不可中斷對話
                logger.warning("危急事件落庫失敗")
            self._notifier.notify(line_user_id, assessment)
        reply_text = self._generate(line_user_id, user_text, trace_id=trace_id)
        result = self._synthesize(reply_text, line_user_id=line_user_id, trace_id=trace_id)
        # 附上本輪的使用者原話（語音為 ASR 辨識、文字為輸入），供 debug 顯示。
        return replace(result, transcript=user_text)
```

- [ ] **Step 4: 執行測試確認通過（含既有語音測試不回歸）**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: PASS（新測試通過，且既有 `process()` 相關測試全數維持綠燈）。

- [ ] **Step 5: Commit**

```bash
git add src/kinsun/pipeline.py tests/test_pipeline.py
git commit -m "feat: VoicePipeline 抽共用核心並新增 process_text（文字輸入路徑）"
```

---

### Task 3: `dispatch` 加旗標分支並抽共用 `_run_pipeline`

**Files:**
- Modify: `src/kinsun/channels/inbound.py:84-121`（`dispatch`）、新增模組級 `_run_pipeline`
- Test: `tests/test_channels_inbound.py`

**Interfaces:**
- Consumes: `VoicePipeline.process` 與 `VoicePipeline.process_text`（Task 2）。
- Produces:
  - `dispatch(msg, *, pipeline, binding, gate, voice=None, traces=None, text_input_enabled: bool = False, timer=time.monotonic) -> None`。
  - 私有 `_run_pipeline(msg, produce, *, voice, traces, timer) -> None`。

- [ ] **Step 1: 更新測試替身並寫失敗測試**

在 `tests/test_channels_inbound.py`：

先擴充檔案頂端的 import（`from kinsun.speech.asr import ASRError` 之後加一行）：

```python
from kinsun.llm import LLMError
```

把既有的 `_Pipeline` fake（第 24-34 行）替換為：

```python
class _Pipeline:
    def __init__(self, text="管線回覆", boom=None):
        self._text = text
        self._boom = boom
        self.calls = []
        self.text_calls = []

    def process(self, audio, *, line_user_id, trace_id="", audio_url=""):
        self.calls.append((audio, line_user_id))
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(text=self._text)

    def process_text(self, text, *, line_user_id, trace_id=""):
        self.text_calls.append((text, line_user_id))
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(text=self._text)
```

在檔案尾端新增測試：

```python
def test_text_flag_on_runs_pipeline():
    r = _Replies()
    pipe = _Pipeline(text="你說的是：哈囉")
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert pipe.text_calls == [("哈囉", "U-1")]
    assert r.sent == ["你說的是：哈囉"]


def test_text_flag_on_binding_command_still_routes_to_binding():
    r = _Replies()
    binding = _Binding("已建立")
    pipe = _Pipeline()
    dispatch(
        _msg("text", text="設定", reply=r),
        pipeline=pipe,
        binding=binding,
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert binding.calls == [("U-1", "設定")]
    assert r.sent == ["已建立"]
    assert pipe.text_calls == []


def test_text_flag_on_blocked_when_gate_denies():
    r = _Replies()
    pipe = _Pipeline()
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(False),
        text_input_enabled=True,
    )
    assert r.sent == [BIND_FIRST_PROMPT]
    assert pipe.text_calls == []


def test_text_flag_on_pipeline_error_replies_fallback():
    r = _Replies()
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=_Pipeline(boom=LLMError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert r.sent == [FALLBACK_PROMPT]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_channels_inbound.py -k "flag_on" -q`
Expected: FAIL —旗標開時非綁定文字仍走舊分支回 `NON_AUDIO_PROMPT`（`text_calls` 為空、`r.sent` 不符）。

- [ ] **Step 3: 實作最小程式**

把 `src/kinsun/channels/inbound.py` 的 `dispatch` 函式（第 84-121 行）整段替換為：

```python
def dispatch(
    msg: InboundMessage,
    *,
    pipeline,
    binding,
    gate,
    voice=None,
    traces: TraceStore | None = None,
    text_input_enabled: bool = False,
    timer: Callable[[], float] = time.monotonic,
) -> None:
    if msg.kind == "text":
        reply = binding.handle(msg.line_user_id, msg.text)
        if reply is not None:
            msg.reply(reply)
            return
        # 非綁定自由文字：旗標關維持只收語音；旗標開才轉進對話管線（Debug）。
        if not text_input_enabled:
            msg.reply(NON_AUDIO_PROMPT)
            return
        if not gate.allows(msg.line_user_id):
            msg.reply(BIND_FIRST_PROMPT)
            return
        _run_pipeline(
            msg,
            lambda: pipeline.process_text(
                msg.text, line_user_id=msg.line_user_id, trace_id=msg.trace_id
            ),
            voice=voice,
            traces=traces,
            timer=timer,
        )
        return
    if msg.kind != "audio":
        msg.reply(NON_AUDIO_PROMPT)
        return
    if not gate.allows(msg.line_user_id):
        msg.reply(BIND_FIRST_PROMPT)
        return
    _run_pipeline(
        msg,
        lambda: pipeline.process(
            msg.audio,
            line_user_id=msg.line_user_id,
            trace_id=msg.trace_id,
            audio_url=msg.audio_url,
        ),
        voice=voice,
        traces=traces,
        timer=timer,
    )


def _run_pipeline(
    msg: InboundMessage,
    produce: Callable[[], TtsResult],
    *,
    voice,
    traces: TraceStore | None,
    timer: Callable[[], float],
) -> None:
    """執行對話管線並發送回覆：語音與文字共用。任一階段失敗回退提示。"""
    try:
        result = produce()
    except (ASRError, LLMError, MemoryError) as exc:
        logger.warning("對話管線失敗（回退提示）：%s: %s", type(exc).__name__, exc)
        msg.reply(FALLBACK_PROMPT)
        return
    started = timer()
    if voice is not None:
        # 「or」容忍測試替身回 None（既有 _SpyVoice 類 fake）。
        outcome = voice.deliver(msg, result) or DeliveryOutcome(kind="text")
    else:
        msg.reply(result.text)
        outcome = DeliveryOutcome(kind="text")
    _record_reply(traces, msg, outcome, started, timer)
```

- [ ] **Step 4: 執行測試確認通過（含既有語音／文字測試不回歸）**

Run: `uv run pytest tests/test_channels_inbound.py -q`
Expected: PASS（新測試通過；`test_text_none_falls_back_to_prompt`、`test_audio_*`、`test_dispatch_records_*` 等既有測試維持綠燈）。

- [ ] **Step 5: Commit**

```bash
git add src/kinsun/channels/inbound.py tests/test_channels_inbound.py
git commit -m "feat: dispatch 支援文字輸入旗標並抽共用 _run_pipeline"
```

---

### Task 4: webhook 與組裝根接線 `text_input_enabled`

**Files:**
- Modify: `src/kinsun/channels/line/webhook.py:29-91`（`_handle_events`、`create_app`）
- Modify: `src/kinsun/app.py:176-186`（`create_app(...)` 呼叫）
- Test: `tests/test_line_webhook.py`

**Interfaces:**
- Consumes: `dispatch(..., text_input_enabled=...)`（Task 3）、`Settings.line_text_input_enabled`（Task 1）。
- Produces: `create_app(..., text_input_enabled: bool = False)`、`_handle_events(..., text_input_enabled: bool = False)`。

- [ ] **Step 1: 更新測試工廠並寫失敗測試（端到端）**

在 `tests/test_line_webhook.py`：

把 `_make_client`（第 124-142 行）替換為（新增 `text_input_enabled` 參數並傳入 `create_app`）：

```python
def _make_client(
    parser,
    messenger,
    asr=None,
    memory=None,
    binding=None,
    gate=None,
    raise_server_exceptions=True,
    text_input_enabled=False,
):
    pipeline = VoicePipeline(
        asr=asr or MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), memory or NullMemory(), NullContext()),
        tts=TextBubbleTts(),
        detector=_NullDetector(),
        notifier=_NullNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    app = create_app(
        parser=parser,
        pipeline=pipeline,
        messenger=messenger,
        binding=binding or _NullBinding(),
        gate=gate or _AllowGate(),
        text_input_enabled=text_input_enabled,
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)
```

在檔案尾端新增測試：

```python
def test_text_input_flag_on_runs_pipeline():
    messenger = FakeMessenger()
    client = _make_client(
        FakeParser([_text_event("哈囉", "U-7")]),
        messenger,
        binding=_NullBinding(),
        text_input_enabled=True,
    )
    resp = client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert resp.status_code == 200
    assert messenger.replies == [("rt-2", "你說的是：哈囉")]


def test_text_input_flag_off_falls_back_to_prompt():
    messenger = FakeMessenger()
    client = _make_client(
        FakeParser([_text_event("哈囉", "U-7")]),
        messenger,
        binding=_NullBinding(),
    )
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.replies == [("rt-2", NON_AUDIO_PROMPT)]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_line_webhook.py -k "text_input_flag" -q`
Expected: FAIL —`create_app` 尚無 `text_input_enabled` 參數（`TypeError: unexpected keyword argument`）。

- [ ] **Step 3: 實作最小程式（webhook 接線）**

在 `src/kinsun/channels/line/webhook.py`：

把 `_handle_events`（第 29-47 行）簽章與 dispatch 呼叫改為：

```python
def _handle_events(
    events,
    *,
    channel: LineChannel,
    pipeline,
    binding,
    gate,
    voice,
    traces=None,
    text_input_enabled: bool = False,
) -> None:
    for event in events:
        try:
            msg = channel.inbound(event)
            if msg is not None:
                dispatch(
                    msg,
                    pipeline=pipeline,
                    binding=binding,
                    gate=gate,
                    voice=voice,
                    traces=traces,
                    text_input_enabled=text_input_enabled,
                )
        except Exception:  # noqa: BLE001
            # 單一事件失敗不可讓 webhook 回 500：LINE 會重送整包事件，
            # 導致重複跑管線、重複發家屬危急通知。記錄後繼續下一個事件。
            logger.exception("處理 LINE 事件失敗")
```

把 `create_app` 簽章（第 50-61 行）新增參數：於 `inbound_audio=None,` 之後、`on_shutdown=...` 之前加：

```python
    text_input_enabled: bool = False,
```

把 route 內 `run_in_threadpool(_handle_events, ...)` 呼叫（第 81-90 行）補上參數，於 `traces=traces,` 之後加：

```python
            text_input_enabled=text_input_enabled,
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest tests/test_line_webhook.py -q`
Expected: PASS（新測試通過；既有 webhook 測試維持綠燈）。

- [ ] **Step 5: 接線組裝根 `app.py`**

在 `src/kinsun/app.py` 的 `create_app(...)` 呼叫（第 176-186 行），於 `inbound_audio=inbound_audio,` 之後加一行：

```python
        text_input_enabled=settings.line_text_input_enabled,
```

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/channels/line/webhook.py src/kinsun/app.py tests/test_line_webhook.py
git commit -m "feat: 接線 LINE_TEXT_INPUT_ENABLED 到 webhook 與組裝根"
```

---

### Task 5: 全測試與靜態檢查驗證

**Files:**
- 無新增；僅執行驗證。

- [ ] **Step 1: 執行完整測試套件**

Run: `uv run pytest -q`
Expected: PASS（全數通過；整合測試若需 `KINSUN_IT=1`／Postgres 未設定則略過，屬預期）。

- [ ] **Step 2: 靜態檢查（若專案有設定）**

Run: `uv run ruff check src/kinsun/config.py src/kinsun/pipeline.py src/kinsun/channels/inbound.py src/kinsun/channels/line/webhook.py src/kinsun/app.py`
Expected: 無錯誤。

- [ ] **Step 3: 人工冒煙（可選，需真實 LINE 環境）**

設 `LINE_TEXT_INPUT_ENABLED=true` 啟動服務，於 LINE 打一句非綁定文字（如「哈囉」），確認金孫以語音（附文字）回覆；打「設定」確認仍走綁定流程；把旗標設回 `false` 確認自由文字回「金孫現在聽得懂語音喔…」。

---

## Self-Review

**1. Spec coverage（逐項對照設計文件）：**
- 設定旗標（設計 §1）→ Task 1 ✓
- 管線抽核心 + `process_text`（設計 §2）→ Task 2 ✓
- `dispatch` 旗標分支 + `_run_pipeline`（設計 §3）→ Task 3 ✓
- webhook/app 接線（設計 §4）→ Task 4 ✓
- 綁定指令優先、gate 沿用、風險偵測照跑（設計決策 3/4/5）→ Task 2（風險）＋Task 3（綁定優先、gate）測試涵蓋 ✓
- 回覆走 `voice.deliver`、失敗退文字（設計決策 2）→ 複用既有 `_run_pipeline`／`VoiceReplyDelivery`，Task 4 端到端驗證 ✓
- `.env.example` 文件同步（設計 §文件）→ Task 1 Step 5 ✓
- 錯誤處理 `(ASRError, LLMError, MemoryError)`→`FALLBACK_PROMPT`（設計 §錯誤處理）→ Task 3 `_run_pipeline` ✓

**2. Placeholder scan：** 無 TBD／TODO；每個程式步驟均附完整程式碼與確切指令。

**3. Type consistency：** `process_text(text, *, line_user_id, trace_id="")`、`_process_transcribed(user_text, *, line_user_id, trace_id)`、`dispatch(..., text_input_enabled=False, ...)`、`create_app(..., text_input_enabled=False)`、`_handle_events(..., text_input_enabled=False)`、`Settings.line_text_input_enabled` 於各 Task 間名稱與簽章一致。
