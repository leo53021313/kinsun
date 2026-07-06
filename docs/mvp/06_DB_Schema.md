# 06 DB Schema — 金孫 KinSun

> **文件性質**：2026-07-06 依 [src/kinsun/db.py](../../src/kinsun/db.py) 的 DDL 逐欄反向抄錄（現況記錄）。
> 全部表定義集中在 `db.py` 一個檔案，repo 內無 migration 工具與 `.sql` 檔。
> ⚠ 標記對應 [全庫人工決策盤點-待議](../全庫人工決策盤點-待議.md)。

**通用慣例**（AGENTS.md 命名規範）：表名複數；主鍵 `<表單數>_id` 全稱（TEXT，應用層填 uuid）；
時間戳 `<動詞過去分詞>_at`、型別 `DOUBLE PRECISION`（epoch 秒）；所有欄位除標註「可空」外皆 NOT NULL；
DDL 無 DEFAULT（皆由應用層填值）。⚠ E-11：所有 TEXT 欄位**無長度上限**。

---

## 1. 資料表總覽（依領域）

| 領域 | 表 | 用途 | 自動清理 |
|------|----|------|---------|
| 短期記憶 | `turns` | 每輪對話逐筆（今日上下文＋夜間整理來源） | ❌ 永久保存 ⚠ T-14 |
| 帳號 | `elders`、`guardians`、`elder_guardians`、`consents`、`invites` | 長輩／家屬／關聯／同意／邀請碼 | ❌ |
| 綁定 | `binding_sessions` | 綁定引導狀態機（每人一列） | ❌（TTL 只影響邏輯不刪列） |
| 排程 | `scheduler_state` | 各 job 最後執行時間 | ❌ |
| 照護 | `medications`、`appointments` | 用藥／回診 | ❌ |
| 安全 | `risk_events` | 危急事件（L 分級＋原因） | ❌ 永久保存 ⚠ T-14 |
| 報告 | `reminder_logs`、`conversation_summaries` | 提醒紀錄／每日對話摘要 | ❌ 永久保存 ⚠ T-14 |
| 觀測 | `webhook_events`、`asr_calls`、`llm_calls`、`tts_calls`、`replies` | 單輪鏈路五表（皆帶 trace_id） | ✅ 保留 `ADMIN_RETENTION_DAYS`＝14 天 |
| 衛教 RAG | `rag_sources`、`rag_documents`、`rag_chunks`、`rag_crawl_jobs`、`rag_ingestion_audit_logs` | 衛教檢索（pgvector 768 維） | ❌ |
| 長期記憶 | `kinsun_memories`（mem0 自管，不在 db.py） | mem0 向量記憶 | ❌ 只增不改 ⚠ T-23 |

## 2. 逐表欄位定義

### 2.1 短期記憶

**`turns`**（db.py MEMORY_DDL）
| 欄位 | 型別 | 說明 |
|------|------|------|
| id | BIGSERIAL PK | |
| line_user_id | TEXT | LINE 平台識別碼（≠ elder_id） |
| role | TEXT | user／assistant |
| content | TEXT | 訊息內容 |
| created_at | DOUBLE PRECISION | |

索引：`idx_turns_line_user_created (line_user_id, created_at)`
⚠ E-08：缺 user_id 的訊息全部落進共用的 `"unknown"` 會話。

### 2.2 帳號綁定

**`elders`**：`elder_id` TEXT PK、`name` TEXT、`line_user_id` TEXT（可空＝未綁定）。
⚠ T-27：一個 LINE 帳號可綁定多個長輩檔（無唯一約束）。

**`guardians`**：`guardian_id` TEXT PK、`line_user_id` TEXT UNIQUE、`name` TEXT。

**`elder_guardians`**（多對多）：PK `(elder_id, guardian_id)`、`role` TEXT、
`escalation_order` INTEGER、`can_view_transcript` BOOLEAN。
⚠ T-26：`escalation_order`／`can_view_transcript` 目前是**死欄位**，通知一律推全體。

**`consents`**：`elder_id` TEXT PK、`consent_by` TEXT（v1 只有 SELF ⚠ T-20）、`version` TEXT
（⚠ T-19：指向不存在的條款）、`granted_at`、`revoked_at`（可空；⚠ T-15：撤回無入口、撤回後資料不刪）。

**`invites`**：`code` TEXT PK（天然唯一鍵當主鍵）、`elder_id`、`role`、`expires_at`
（TTL 24h）、`max_attempts` INTEGER（5，死設定 ⚠ T-29）、`attempts` INTEGER、`used_at`（可空）。

### 2.3 綁定會話／排程狀態

**`binding_sessions`**：`line_user_id` TEXT PK、`state` TEXT（合法值＝`BindingState` StrEnum）、
`data` TEXT（JSON 字串）、`updated_at`。

**`scheduler_state`**（key-value 例外命名）：`job_name` TEXT PK、`last_run_at`。

### 2.4 照護

**`medications`**：`medication_id` TEXT PK、`elder_id`、`name` TEXT（自由文字無驗證，
無劑量／備註欄位 ⚠ T-34）、`slots` TEXT（逗號串接，如 `morning,noon`）。

**`appointments`**：`appointment_id` TEXT PK、`elder_id`、`date` TEXT（ISO 字串 ⚠ T-46）、`label` TEXT。
索引：`idx_appointments_date (date)`。

### 2.5 安全與報告

**`risk_events`**：`risk_event_id` TEXT PK、`line_user_id`、`tier` INTEGER（0–3）、
`reason` TEXT（LLM 轉述，可能含長輩發言 ⚠ T-17）、`created_at`、`trace_id` TEXT（可空，後補欄位）。
索引：`idx_risk_events_line_user_created`。

**`reminder_logs`**（append-only）：`reminder_log_id` TEXT PK、`elder_id`、`kind` TEXT
（medication／appointment／proactive-greeting／proactive-care）、`content`、`created_at`。
索引：`idx_reminder_logs_elder_created`。

**`conversation_summaries`**：PK `(line_user_id, date)`、`content`、`created_at`。
⚠ T-18：摘要無揭露邊界。

### 2.6 觀測五表（append-only，皆帶 `trace_id`）

| 表 | 專屬欄位（皆另有 `*_id` PK、trace_id、line_user_id、created_at） |
|----|------------------------------------------------------------------|
| `webhook_events` | event_type、message_type、payload JSONB |
| `asr_calls` | status、latency_ms INTEGER、transcript、source_audio_url、error_message |
| `llm_calls` | status、latency_ms、model_name、input_tokens（可空）、output_tokens（可空）、content、error_message |
| `tts_calls` | status、latency_ms、content、error_message |
| `replies` | kind、status、latency_ms、audio_url |

各表皆有 `idx_*_trace (trace_id)` 與 `idx_*_created (created_at)`；
`asr_calls` 另有 `idx_asr_calls_line_user_created`。
⚠ T-14：`transcript`／`content` 即對話逐字稿，保留 14 天後清理（其餘表無此保障）。

### 2.7 衛教 RAG（前置 `CREATE EXTENSION IF NOT EXISTS vector`）

**`rag_sources`**：`source_id` TEXT PK、title、url、publisher、source_type、trust_level、
copyright_status（⚠ T-50：授權欄位全由 AI 預填）、recommended_status、approved_for_rag BOOLEAN、
allowed_domains、notes。

**`rag_documents`**：`document_id` TEXT PK、`source_id` FK→rag_sources、url、title、publisher、
text、content_hash、source_type、language、topic、audience、medical_scope、trust_level、
copyright_status、published_at DATE（可空）、updated_at DATE（可空）、retrieved_at DATE。
索引：UNIQUE `(source_id, content_hash)`、`idx_rag_documents_source`。

**`rag_chunks`**：`chunk_id` TEXT PK、`document_id` FK ON DELETE CASCADE、`source_id` FK、text、
`embedding vector(768)`（可空）、（其餘 metadata 欄位同 documents）、last_reviewed_at DATE（可空）、
version TEXT（可空）。索引：`(source_id, topic)`、HNSW `vector_cosine_ops`。

**`rag_crawl_jobs`**：`job_id` TEXT PK、source_id、started_at、finished_at（可空）、status、
page_count INTEGER、error_message（可空）。

**`rag_ingestion_audit_logs`**：id BIGSERIAL PK、source_id、fetched_at、content_hash、
chunk_count、parser_used、status、error_message（可空）、operator_or_job_id。

### 2.8 mem0 自管表

**`kinsun_memories`**：由 mem0 supabase provider 自行建立（`mem0_factory.py`：768 維、HNSW、
cosine），欄位結構由 mem0 決定，非本專案 DDL。
⚠ T-16：mem0 內部 history 預設落**本機 SQLite**（`~/.mem0/history.db`），本專案未設定路徑、
未納入任何保留／刪除策略。

## 3. Schema 建立與演進

- 統一入口 `ensure_schema()`（db.py）：取交易級 advisory lock（鎖鍵 4_242_001，避免 webhook 與
  scheduler 併發建表死結）→ 依序執行全部 DDL → commit。呼叫點：`composition.build_externals`
  （app 與 scheduler 啟動時）、`rag/ingest.py`（CLI）。
- 冪等：全部 `CREATE ... IF NOT EXISTS`；唯一欄位演進為
  `ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS trace_id`。
- ⚠ E-04：**無 migration 工具**——改既有欄位（改型別、改約束）不會生效，只能加表加欄；
  後續 schema 演進策略待拍板。

## 4. 連線與設定

- `Database`（db.py）包 `psycopg_pool.ConnectionPool`，**min 1／max 5、無逾時設定** ⚠ E-04。
- 連線字串：`DATABASE_URL`（必填）——短期記憶＋帳號＋觀測＋RAG＋mem0 向量全共用同一庫。
- Supabase Storage（音檔）另用 `SUPABASE_URL`／`SUPABASE_SERVICE_KEY`（非 DB 連線）。
- 所有 Store 例外統一翻成 `StoreError`（RAG 為 `RagStoreError`）。

## 5. 持久層三件套（Store 目錄）

每領域固定 `<領域>Store`（Protocol）＋`Pg<領域>Store`＋`Fake<領域>Store` 同住 `store.py`，
合約測試見 [08_Test_Checklist](08_Test_Checklist.md) §1：

| 領域 | 檔案 | 主要方法 |
|------|------|----------|
| accounts | `accounts/store.py` | save/get_elder、save/get_guardian、save_elder_guardian、list_elder_guardians、elder_ids_of_guardian、save/get_consent、save/get_invite、transaction |
| medications | `medications/store.py` | save、list_for_elder、list_for_slot、remove |
| appointments | `appointments/store.py` | save、list_for_elder、list_for_date、remove |
| binding | `binding/session.py` | get、save、delete |
| memory（短期） | `memory/shortterm.py` | append、recent、previous_day、sessions、last_active |
| memory（長期） | `memory/longterm/store.py` | add、search（Fake 在 `tests/fakes.py`，語意檢索不納合約） |
| observability | `observability/store.py` | record_×5、get_trace、list_feed、list_timeline_for_elder、list_elders_with_last_active、get_overview_stats、purge_older_than |
| safety | `safety/events.py` | record、list_for_line_user |
| reports | `reports/reminders.py`、`reports/summaries.py` | record／list_for_elder；save／list_for_line_user |
| scheduler | `scheduler/state.py` | get_last_run、set_last_run |
| rag | `rag/vector_store.py` | upsert_source/document、add、search、keyword_search、log_ingestion、reset |

## 6. 資料保留現況（法遵重點 ⚠ T-14／T-15／T-24）

| 資料 | 保留策略 |
|------|----------|
| 觀測五表 | ✅ 每日 03:45 清理，保留 `ADMIN_RETENTION_DAYS`（14 天） |
| TTS／進站音檔（Supabase Storage） | ✅ 每日清理，保留 `AUDIO_RETENTION_DAYS`（2 天）；⚠ T-24：依賴 scheduler worker 有人啟動 |
| `turns`（逐字稿）、`risk_events`、`reminder_logs`、`conversation_summaries` | ❌ **永久保存，無任何保留期限決策** ⚠ T-14 |
| `consents.revoked_at` | 撤回後**不刪任何資料**，且無撤回入口 ⚠ T-15 |
| mem0 `kinsun_memories`＋本機 history.db | ❌ 只增不刪 ⚠ T-16／T-23 |
