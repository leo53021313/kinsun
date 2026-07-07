# 07 Tech Design — 金孫 KinSun

> **文件性質**：2026-07-06 依程式碼現況反向工程的技術設計總覽（as-is）。
> 領域語彙見 [CONTEXT.md](../../CONTEXT.md)（唯一來源）；各模組細部設計見
> [docs/superpowers/specs/](../superpowers/specs/)；⚠ 標記對應 [全庫人工決策盤點-待議](../全庫人工決策盤點-待議.md)。

---

## 1. 技術棧

| 層 | 選型 |
|----|------|
| 語言／工具 | Python 3.12、uv、ruff、pre-commit、pytest（後端無 mypy） |
| Web | FastAPI＋uvicorn（factory：`kinsun.app:build_app`）、line-bot-sdk v3 |
| LLM／Embedding | Gemini `gemini-3.1-flash-lite`（對話/分級/抽取/摘要統包 ⚠ T-48）、`gemini-embedding-001`（768 維） |
| 長期記憶 | Mem0 v1.1（vector_store=supabase/pgvector，collection `kinsun_memories`） |
| 資料庫 | Supabase Postgres（psycopg v3＋連線池 1–5 ⚠ E-04），單一 `DATABASE_URL` 共用 |
| 語音 | ASR：Breeze-ASR-26（DGX :8001）；TTS：CosyVoice 3（DGX :8002）——皆為獨立 FastAPI sidecar，**無認證** ⚠ T-49 |
| 音檔 | Supabase Storage 公開 bucket（`tts/`、`inbound/` 前綴、日期資料夾） |
| 前端 | React 18＋TypeScript＋Vite 6，兩個 SPA（`/liff` 家屬端、`/admin` 觀測後台），後端同源供應 |
| 排程 | 自製 `Scheduler`（croniter，每日 cron），獨立 worker 行程 |
| 部署 | DGX Spark（aarch64）＋ngrok 對外；`scripts/kinsun.sh` 啟停 6 個行程 |

## 2. 行程拓撲與組裝

```
┌────────────── DGX Spark ──────────────┐
│ webhook app :8000 ←── ngrok ←── LINE  │
│   ├─ /line/webhook（驗簽）            │
│   ├─ /api（LIFF idToken）             │      Supabase（雲端）
│   ├─ /api/admin（X-Admin-Key）        │   ┌──────────────────┐
│   └─ /liff、/admin（靜態 SPA）        │──▶│ Postgres+pgvector │
│ scheduler worker（python -m kinsun.   │──▶│ Storage（音檔）    │
│   scheduler，tick 60s）               │   └──────────────────┘
│ ASR :8001（GPU）  TTS :8002（GPU）     │      Gemini API
└───────────────────────────────────────┘
```

**組裝根**（`composition.py`）：`build_externals(settings)` 建外部相依（DB 池、Gemini、mem0、
LINE、`ensure_schema`）→ `assemble_core(settings, externals, clock)` 純接線組出共用物件圖
`Core`（frozen dataclass，可離線測）→ `build_app`／`build_scheduler` 各自補 edge-specific 接線
（pipeline／jobs）。啟動**必須**雲端金鑰（`DATABASE_URL`、`GEMINI_API_KEY`、LINE）。

## 3. 入站管線（單輪對話）

```
POST /line/webhook（async，驗簽）
 └─ run_in_threadpool(_handle_events)          ← 同步跑完整管線 ⚠ T-42
     └─ LineChannel.inbound：trace_id、record_webhook_event、下載/備份音檔
         └─ dispatch（channels/inbound.py）
             ├─ 綁定狀態機 BindingFlow（binding/flow.py）
             ├─ 閘門 ConsentGate（fail-open ⚠ T-10）
             └─ VoicePipeline（pipeline.py，_span 觀測埋點）
                 ├─ _transcribe → ASRClient（mock↔dgx 可切）
                 ├─ detector.assess（keywords＋LlmRiskClassifier，fail-safe L0 ⚠ T-05）
                 ├─ tier≥L2：risk_events.record → LineGuardianNotifier ← 先於回覆生成
                 ├─ _generate → CareAgent（SessionMemory 注入＋工具迴圈≤3）
                 └─ _synthesize → TTSClient（TTSError → 退化純文字）
             └─ VoiceReplyDelivery.deliver（語音失敗退文字泡泡）
```

fail-safe 原則：記憶／LLM／DB／TTS 任一失敗都退化、不中斷對話；觀測 `record_*` 失敗絕不中斷。

## 4. 記憶三層

| 層 | 實作 | 內容 |
|----|------|------|
| shortterm | `PgMemoryStore`（`turns` 表） | 今日對話，`recent`（≤`MEMORY_MAX_TURNS`=200 ⚠ E-13）、`previous_day`（夜間整理源） |
| longterm | `Mem0LongTermStore`（mem0＋pgvector） | 跨日長者事實；`search` 每輪固定追加健康事實檢索（top_k 寫死 ⚠ E-16）；抽取 prompt ⚠ T-21 |
| recall | `SessionMemory`（`memory/recall.py`） | `assemble` 組 `TurnContext`（今日對話＋長期記憶＋用藥/回診事實）；agent 只碰此門面 |

已知降級：mem0 supabase 不支援 BM25；entity linking 缺 spaCy 降級；
矛盾事實以「讀取時 created_at 新覆舊」消解（⚠ T-23 只增不改）。

## 5. 排程 job 一覽（自製 Scheduler，狀態存 `scheduler_state`）

| job | 時間（預設） | 內容 |
|-----|------------|------|
| daily-consolidation | 03:00 | 長期記憶整理＋當日摘要（⚠ E-14 停機跨日無回填） |
| inbound-audio-cleanup | 03:00 | 進站音檔清理（保留 2 天） |
| audio-cleanup | 03:30 | TTS 音檔清理（僅 dgx） |
| observability-cleanup | 03:45 | 觀測五表清理（保留 14 天） |
| daily-greeting | 08:00 | 早安問候（不過同意閘門 ⚠ T-30） |
| medication-morning/noon/evening/bedtime | 8/12/18/21 ⚠ T-33 | 用藥提醒 |
| appointment-reminder | 08:00 | 回診提醒（長輩＋家屬） |
| inactivity-care | 10:00 | 失聯關心（>2 天） |

worker 無存活監控 ⚠ E-17：行程死掉＝所有提醒靜默停止。job 無手動觸發 CLI。

## 6. 前端技術設計（老師指南 §7.2 格式）

**Route**：見 [04_Wireframe](04_Wireframe.md) §3／§4。
**Component tree**（家屬端）：`App`（liff.init＋Router）→ `EldersPage`／`MedicationsPage`／
`AppointmentsPage`／`HealthReportPage`；API 封裝集中 `frontend/src/api.ts`（admin 另有
`admin/api.ts` 含完整 TS 型別）。
**State**：無狀態庫，各頁 `useState`＋fetch；admin 訊息流 5 秒輪詢帶 `after` 游標。
**API 合約**：見 [05_API_Spec](05_API_Spec.yaml)；JSON 欄位 snake_case 前後端一致。
**Error handling**：`ApiError(status)` 統一丟出；401 清狀態（無重新登入提示 ⚠ E-09）；
深層路徑 F5 得 404 ⚠ E-10；建置 `npm run build`＋`build:admin` 後由後端供應。

## 7. 設定（環境變數）

`Settings`（frozen dataclass）欄位＝環境變數鍵小寫，100% 一一對應，全數列於
[.env.example](../../.env.example)。必填：`LINE_CHANNEL_SECRET`／`LINE_CHANNEL_ACCESS_TOKEN`／
`GEMINI_API_KEY`／`DATABASE_URL`。其餘依前綴分組：`GEMINI_`、`ASR_`、`TTS_`、`AUDIO_`、
`SUPABASE_`、`LONGTERM_`、`MEMORY_`、`PROACTIVE_`、`SCHEDULER_`、`MEDICATION_`、`APPOINTMENT_`、
`INVITE_`、`BINDING_`、`LIFF_`、`RICH_MENU_ID`、`ADMIN_`、`RAG_`。
不經 config 的部署層鍵：`NGROK_*`、`LIFF_ID`（richmenu CLI）、DGX 服務端 `ASR_*`/`TTS_*`
（見各自 README）。⚠ E-01：`GEMINI_TIMEOUT_SECONDS` 讀入後未套用；⚠ E-12：`LIFF_CHANNEL_ID`
未設不擋啟動。

## 8. 橫切面設計（seams）

| Seam | 介面 | 正式／替身 |
|------|------|-----------|
| HTTP 出站 | `Transport`（`transport.py`） | `UrllibTransport`／FakeTransport（測試注入，不 monkeypatch） |
| 訊息出站 | `OutboundChannel`（`channels/outbound.py`） | `LineOutboundChannel`（push）／fake |
| 訊息入站 | `InboundMessage`＋`dispatch` | LINE adapter 正規化，分派邏輯不碰 SDK |
| 持久層 | `<領域>Store` Protocol ×11 | `Pg*`／`Fake*` 同住 store.py，合約測試保證等價 |
| 觀測 | `TraceStore`＋pipeline `_span` | `PgTraceStore`／`FakeTraceStore`；失敗不中斷 |
| 模型服務 | `ASRClient`／`TTSClient`／`AudioPublisher` | mock↔dgx 環境變數切換，位置無關 |

## 9. 安全設計現況（誠實盤點）

- 三組驗證：LINE HMAC 驗簽、LIFF idToken（LINE verify API）、Admin 常數時間比對金鑰。✅
- 家屬只能操作自己的長輩（`assert_manages`）。✅
- 已知缺口：DGX sidecar 無認證 ⚠ T-49；權限分級未落地（人人皆主家屬）⚠ T-26；
  邀請碼無速率限制 ⚠ T-29；文字欄位無長度上限 ⚠ E-11；LINE SDK 呼叫無逾時 ⚠ E-18；
  Gemini 無 temperature/max_tokens/重試設定 ⚠ E-02。
- Secrets 全走環境變數，無寫死。✅（mem0 遙測已關）
