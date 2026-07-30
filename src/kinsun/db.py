"""共用 Postgres 連線、連線池與建表 DDL（Supabase）。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Protocol

import psycopg
from psycopg_pool import ConnectionPool

# elder_id 相關索引不放這裡：既有舊表要等 SESSION_KEY_MIGRATION_DDL 補完欄位才能建，
# 該遷移（於 ensure_schema 最後執行）已含同名冪等索引，新庫舊庫皆適用。
MEMORY_DDL = (
    "CREATE TABLE IF NOT EXISTS turns ("
    "id BIGSERIAL PRIMARY KEY, elder_id TEXT, role TEXT NOT NULL, "
    "content TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
)

ACCOUNTS_DDL = (
    "CREATE TABLE IF NOT EXISTS elders ("
    "elder_id TEXT PRIMARY KEY, name TEXT NOT NULL);"
    # 稱謂欄（2026-07-17）：既有庫走 ALTER 升級（建表→遷移順序，同 appointments.time）。
    "ALTER TABLE elders ADD COLUMN IF NOT EXISTS nickname TEXT NOT NULL DEFAULT '';"
    "CREATE TABLE IF NOT EXISTS guardians ("
    "guardian_id TEXT PRIMARY KEY, name TEXT NOT NULL);"
    "CREATE TABLE IF NOT EXISTS elder_guardians ("
    "elder_id TEXT NOT NULL, guardian_id TEXT NOT NULL, role TEXT NOT NULL, "
    "escalation_order INTEGER NOT NULL, "
    "PRIMARY KEY (elder_id, guardian_id));"
    "CREATE TABLE IF NOT EXISTS consents ("
    "elder_id TEXT PRIMARY KEY, consent_by TEXT NOT NULL, version TEXT NOT NULL, "
    "granted_at DOUBLE PRECISION NOT NULL, revoked_at DOUBLE PRECISION);"
    "CREATE TABLE IF NOT EXISTS invites ("
    "code TEXT PRIMARY KEY, elder_id TEXT NOT NULL, role TEXT NOT NULL, "
    "expires_at DOUBLE PRECISION NOT NULL, max_attempts INTEGER NOT NULL, "
    "attempts INTEGER NOT NULL, used_at DOUBLE PRECISION);"
)

APP_ACCOUNTS_DDL = (
    "CREATE TABLE IF NOT EXISTS guardian_accounts ("
    "guardian_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
    "password_hash TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE TABLE IF NOT EXISTS elder_accounts ("
    "elder_id TEXT PRIMARY KEY, phone TEXT NOT NULL UNIQUE, "
    "password_hash TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE TABLE IF NOT EXISTS api_tokens ("
    "token_hash TEXT PRIMARY KEY, principal_type TEXT NOT NULL, "
    "principal_id TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
)

CHANNEL_BINDINGS_DDL = (
    "CREATE TABLE IF NOT EXISTS channel_bindings ("
    "channel TEXT NOT NULL, external_id TEXT NOT NULL, "
    "principal_type TEXT NOT NULL, principal_id TEXT NOT NULL, "
    "created_at DOUBLE PRECISION NOT NULL, "
    "PRIMARY KEY (channel, external_id));"
    "CREATE INDEX IF NOT EXISTS idx_channel_bindings_principal "
    "ON channel_bindings (principal_type, principal_id);"
)

BINDING_DDL = (
    "CREATE TABLE IF NOT EXISTS binding_sessions ("
    "line_user_id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL, "
    "updated_at DOUBLE PRECISION NOT NULL);"
)

SCHEDULER_DDL = (
    "CREATE TABLE IF NOT EXISTS scheduler_state ("
    "job_name TEXT PRIMARY KEY, last_run_at DOUBLE PRECISION NOT NULL);"
)

# 認證節流共享計數（✅ 庚-08／A-54）：多 worker 共用同一滑動視窗，避免 per-process
# 上限×worker 數放大暴力破解面。每筆＝一次嘗試（key＝scope:ip、hit_at＝掛鐘秒）；
# 過期列於同鍵下次 hit 時清除。
RATE_LIMIT_DDL = (
    "CREATE TABLE IF NOT EXISTS rate_limit_hits ("
    "key TEXT NOT NULL, hit_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_rate_limit_hits_key_time "
    "ON rate_limit_hits (key, hit_at);"
)

# 舊的用藥與回診表（D-76 P5 退役）：資料已遷入 schedules，全庫無人讀寫。
# 用 DROP 而非留著不管——留著會讓下一個人以為那還是真相來源，而它的內容自 P3
# 家屬入口切換後就再也不會更新了。既有庫執行一次即清乾淨，新庫是 no-op。
LEGACY_REMINDER_TABLES_RETIRE_DDL = (
    "DROP TABLE IF EXISTS medications;DROP TABLE IF EXISTS appointments;"
)

SCHEDULES_DDL = (
    "CREATE TABLE IF NOT EXISTS schedules ("
    "schedule_id TEXT PRIMARY KEY, group_id TEXT NOT NULL, elder_id TEXT NOT NULL, "
    "kind TEXT NOT NULL, title TEXT NOT NULL, repeat_kind TEXT NOT NULL, "
    "scheduled_at DOUBLE PRECISION, repeat_time TEXT NOT NULL DEFAULT '', "
    "repeat_weekday INTEGER, event_at DOUBLE PRECISION, "
    "audience TEXT NOT NULL DEFAULT 'elder', created_by TEXT NOT NULL, "
    "created_at DOUBLE PRECISION NOT NULL, cancelled_at DOUBLE PRECISION, "
    "settled_at DOUBLE PRECISION, fired_at DOUBLE PRECISION);"
    "CREATE INDEX IF NOT EXISTS idx_schedules_elder_active "
    "ON schedules (elder_id, cancelled_at);"
    "CREATE INDEX IF NOT EXISTS idx_schedules_group ON schedules (group_id);"
    "CREATE INDEX IF NOT EXISTS idx_schedules_repeat ON schedules (repeat_time) "
    "WHERE cancelled_at IS NULL;"
    "CREATE INDEX IF NOT EXISTS idx_schedules_due_once ON schedules (scheduled_at) "
    "WHERE cancelled_at IS NULL AND settled_at IS NULL;"
)

RAG_DDL = (
    "CREATE EXTENSION IF NOT EXISTS vector;"
    "CREATE TABLE IF NOT EXISTS rag_sources ("
    "source_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL, "
    "publisher TEXT NOT NULL, source_type TEXT NOT NULL, trust_level TEXT NOT NULL, "
    "copyright_status TEXT NOT NULL, recommended_status TEXT NOT NULL, "
    "approved_for_rag BOOLEAN NOT NULL, allowed_domains TEXT NOT NULL, notes TEXT NOT NULL, "
    "source_role TEXT NOT NULL DEFAULT 'answer');"
    "ALTER TABLE rag_sources ADD COLUMN IF NOT EXISTS source_role TEXT NOT NULL DEFAULT 'answer';"
    "CREATE TABLE IF NOT EXISTS rag_documents ("
    "document_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES rag_sources(source_id), "
    "url TEXT NOT NULL, title TEXT NOT NULL, publisher TEXT NOT NULL, text TEXT NOT NULL, "
    "content_hash TEXT NOT NULL, source_type TEXT NOT NULL, language TEXT NOT NULL, "
    "topic TEXT NOT NULL, audience TEXT NOT NULL, medical_scope TEXT NOT NULL, "
    "trust_level TEXT NOT NULL, copyright_status TEXT NOT NULL, "
    "published_at DATE, updated_at DATE, retrieved_at DATE NOT NULL);"
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_documents_source_hash "
    "ON rag_documents (source_id, content_hash);"
    "CREATE INDEX IF NOT EXISTS idx_rag_documents_source ON rag_documents (source_id);"
    "CREATE TABLE IF NOT EXISTS rag_chunks ("
    "chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES rag_documents(document_id) "
    "ON DELETE CASCADE, source_id TEXT NOT NULL REFERENCES rag_sources(source_id), "
    "text TEXT NOT NULL, embedding vector(768), title TEXT NOT NULL, publisher TEXT NOT NULL, "
    "source_url TEXT NOT NULL, source_type TEXT NOT NULL, language TEXT NOT NULL, "
    "topic TEXT NOT NULL, audience TEXT NOT NULL, medical_scope TEXT NOT NULL, "
    "trust_level TEXT NOT NULL, approved_for_rag BOOLEAN NOT NULL, "
    "copyright_status TEXT NOT NULL, source_published_at DATE, source_updated_at DATE, "
    "retrieved_at DATE NOT NULL, last_reviewed_at DATE, version TEXT, "
    "source_role TEXT NOT NULL DEFAULT 'answer', embedding_model TEXT NOT NULL DEFAULT '');"
    "ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS source_role TEXT NOT NULL DEFAULT 'answer';"
    "ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS embedding_model TEXT NOT NULL DEFAULT '';"
    "CREATE INDEX IF NOT EXISTS idx_rag_chunks_source_topic ON rag_chunks (source_id, topic);"
    "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding "
    "ON rag_chunks USING hnsw (embedding vector_cosine_ops);"
    # rag_crawl_jobs 死表已退役（✅ 庚-34／A-31：無寫入者）。
    "DROP TABLE IF EXISTS rag_crawl_jobs;"
    "CREATE TABLE IF NOT EXISTS rag_ingestion_audit_logs ("
    "id BIGSERIAL PRIMARY KEY, source_id TEXT NOT NULL, fetched_at DOUBLE PRECISION NOT NULL, "
    "content_hash TEXT NOT NULL, chunk_count INTEGER NOT NULL, parser_used TEXT NOT NULL, "
    "status TEXT NOT NULL, error_message TEXT, operator_or_job_id TEXT NOT NULL, "
    "document_id TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '');"
    "ALTER TABLE rag_ingestion_audit_logs "
    "ADD COLUMN IF NOT EXISTS document_id TEXT NOT NULL DEFAULT '';"
    "ALTER TABLE rag_ingestion_audit_logs ADD COLUMN IF NOT EXISTS url TEXT NOT NULL DEFAULT '';"
    "CREATE INDEX IF NOT EXISTS idx_rag_ingestion_audit_fetched "
    "ON rag_ingestion_audit_logs (fetched_at);"
    "CREATE TABLE IF NOT EXISTS rag_index_releases ("
    "index_version TEXT PRIMARY KEY, status TEXT NOT NULL, embedding_model TEXT NOT NULL, "
    "embedding_dimensions INTEGER NOT NULL, content_policy TEXT NOT NULL, "
    "quality_metrics JSONB NOT NULL DEFAULT '{}'::jsonb, "
    "relevance_threshold DOUBLE PRECISION, started_at DOUBLE PRECISION NOT NULL, "
    "completed_at DOUBLE PRECISION, published_at DOUBLE PRECISION, error_message TEXT);"
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_release_building "
    "ON rag_index_releases (status) WHERE status = 'building';"
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_release_active "
    "ON rag_index_releases (status) WHERE status = 'active';"
    "CREATE TABLE IF NOT EXISTS rag_release_documents ("
    "index_version TEXT NOT NULL REFERENCES rag_index_releases(index_version) ON DELETE CASCADE, "
    "document_id TEXT NOT NULL REFERENCES rag_documents(document_id) ON DELETE CASCADE, "
    "PRIMARY KEY (index_version, document_id));"
    "CREATE INDEX IF NOT EXISTS idx_rag_release_documents_document "
    "ON rag_release_documents (document_id);"
    "CREATE TABLE IF NOT EXISTS rag_release_chunks ("
    "index_version TEXT NOT NULL REFERENCES rag_index_releases(index_version) ON DELETE CASCADE, "
    "chunk_id TEXT NOT NULL REFERENCES rag_chunks(chunk_id) ON DELETE CASCADE, "
    "PRIMARY KEY (index_version, chunk_id));"
    "CREATE INDEX IF NOT EXISTS idx_rag_release_chunks_chunk "
    "ON rag_release_chunks (chunk_id);"
)

RISK_EVENTS_DDL = (
    "CREATE TABLE IF NOT EXISTS risk_events ("
    "risk_event_id TEXT PRIMARY KEY, elder_id TEXT, "
    "tier INTEGER NOT NULL, reason TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
)

REMINDER_LOGS_DDL = (
    "CREATE TABLE IF NOT EXISTS reminder_logs ("
    "reminder_log_id TEXT PRIMARY KEY, elder_id TEXT NOT NULL, "
    "kind TEXT NOT NULL, content TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_reminder_logs_elder_created "
    "ON reminder_logs (elder_id, created_at);"
)

# 策略記憶（spec 2026-07-14）：金孫每晚反思學到的「相處之道」守則。
# 全新表、無舊欄位要遷移，故建表與建索引可同批（既有庫首次跑時一起建起來）。
STRATEGIES_DDL = (
    "CREATE TABLE IF NOT EXISTS strategies ("
    "strategy_id TEXT PRIMARY KEY, elder_id TEXT NOT NULL, content TEXT NOT NULL, "
    "category TEXT NOT NULL, evidence TEXT NOT NULL, observed_days INTEGER NOT NULL, "
    "status TEXT NOT NULL, supersedes_strategy_id TEXT, "
    "created_at DOUBLE PRECISION NOT NULL, revoked_at DOUBLE PRECISION);"
    "CREATE INDEX IF NOT EXISTS idx_strategies_elder_status "
    "ON strategies (elder_id, status);"
)

# 每位長輩的問候時間偏好（spec 2026-07-16）：夜間批次算、問候 job 讀。
# 全新表、無舊欄位要遷移，故建表可單批（既有庫首次跑時一起建起來）。
GREETING_PREFERENCES_DDL = (
    "CREATE TABLE IF NOT EXISTS greeting_preferences ("
    "elder_id TEXT PRIMARY KEY, hour INTEGER NOT NULL, minute INTEGER NOT NULL, "
    "computed_at DOUBLE PRECISION NOT NULL, sample_days INTEGER NOT NULL, "
    "median_minute_of_day INTEGER NOT NULL);"
)

# 長輩目前地點（spec 2026-07-17）：一位長輩一列、覆寫式，不留行蹤軌跡。
# elder_id 為天然唯一鍵，直接當主鍵（比照 greeting_preferences）。
# 不建額外索引：主鍵即唯一查詢維度。
# ⚠️ 座標欄位不在此處——本表已於 PR #55 上線，見下方 MIGRATION_DDL。
ELDER_LOCATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS elder_locations ("
    "elder_id TEXT PRIMARY KEY, place TEXT NOT NULL, "
    "recorded_at DOUBLE PRECISION NOT NULL);"
)

# 模糊座標（spec 2026-07-17-天氣地點正確性）：手機端四捨五入到 0.01 度（約 1.1
# 公里）後上傳，天氣工具直接拿去查預報、跳過地理編碼——Open-Meteo 的台灣地名
# 索引只有 6/22 縣市命中，而手機回報的正是「台南市」這種查不到的字串。
#
# ⚠️ 既有庫的 elder_locations 早已存在（PR #55 今早合併），CREATE TABLE IF NOT
# EXISTS 對它是 no-op、不會生出座標欄；故新欄位必須獨立以 ALTER 補（把欄位加進
# ELDER_LOCATIONS_DDL 只有新庫吃得到，既有庫永遠缺欄位、線上炸 UndefinedColumn）。
# ensure_schema 裡本段須排在 ELDER_LOCATIONS_DDL 之後——新庫要先有表才 ALTER 得動。
#
# NULL＝我們不知道它在哪（PR #55 寫入的既有列即此情形），語意正確；LocationFacts
# 讀到 NULL 時退回只注入地名。
ELDER_LOCATIONS_COORDS_MIGRATION_DDL = (
    "ALTER TABLE elder_locations ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;"
    "ALTER TABLE elder_locations ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;"
)

# 提醒回應訊號（spec 2026-07-14）：長輩在提醒發出後的時間窗內有發言即標記。
# ⚠️ 既有庫的 reminder_logs 早已存在，CREATE TABLE IF NOT EXISTS 對它是 no-op、
# 不會生出 responded_at；故新欄位必須獨立以 ALTER 補（把欄位加進 REMINDER_LOGS_DDL
# 只有新庫吃得到，既有庫永遠缺欄位）。ensure_schema 裡本段須排在 REMINDER_LOGS_DDL
# 之後——新庫要先有表才 ALTER 得動；新索引引用 responded_at，故與 ALTER 同批（本段內
# 先 ALTER 後建索引），reminder_logs 沒有獨立的索引步驟。
# NULL＝未回應，既有列自動為 NULL，語意正確。
REMINDER_LOGS_RESPONDED_MIGRATION_DDL = (
    "ALTER TABLE reminder_logs ADD COLUMN IF NOT EXISTS responded_at DOUBLE PRECISION;"
    "CREATE INDEX IF NOT EXISTS idx_reminder_logs_elder_responded "
    "ON reminder_logs (elder_id, responded_at);"
)

# 危急通知送達紀錄（✅ D-36，丙-7）：每位家屬成功／失敗獨立留痕。
# channels 記實際走的通道（✅ 庚-16，逗號串接）；App＝落庫待拉取、非真送達。
RISK_NOTIFICATION_LOGS_DDL = (
    "CREATE TABLE IF NOT EXISTS risk_notification_logs ("
    "risk_notification_log_id TEXT PRIMARY KEY, elder_id TEXT NOT NULL, "
    "guardian_id TEXT NOT NULL, tier INTEGER NOT NULL, delivered BOOLEAN NOT NULL, "
    "created_at DOUBLE PRECISION NOT NULL, channels TEXT NOT NULL DEFAULT '');"
    "CREATE INDEX IF NOT EXISTS idx_risk_notification_logs_elder_created "
    "ON risk_notification_logs (elder_id, created_at);"
    "ALTER TABLE risk_notification_logs "
    "ADD COLUMN IF NOT EXISTS channels TEXT NOT NULL DEFAULT '';"
)

# App 內通知（✅ D-12，甲-6）：App 出站 adapter 落地訊息，登入後拉取。
APP_NOTIFICATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS app_notifications ("
    "app_notification_id TEXT PRIMARY KEY, external_id TEXT NOT NULL, "
    "content TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_app_notifications_external_created "
    "ON app_notifications (external_id, created_at);"
)

# 整理進度標記（✅ 庚-06／庚-13）：某長輩某日已整理進長期記憶，供冪等與跨多日補齊。
MEMORY_CONSOLIDATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS memory_consolidations ("
    "elder_id TEXT NOT NULL, day TEXT NOT NULL, turn_count INTEGER NOT NULL, "
    "created_at DOUBLE PRECISION NOT NULL, PRIMARY KEY (elder_id, day));"
)

CONVERSATION_SUMMARIES_DDL = (
    "CREATE TABLE IF NOT EXISTS conversation_summaries ("
    "elder_id TEXT, date TEXT NOT NULL, "
    "content TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
)

# 上網查證來源紀錄（spec 2026-07-14）：金孫每次 web_search 的關鍵字、主題與來源清單。
# 全新表、無舊欄位要遷移，故建表與建索引可同批（既有庫首次跑時一起建起來）。
WEB_SEARCH_LOOKUPS_DDL = (
    "CREATE TABLE IF NOT EXISTS web_search_lookups ("
    "web_search_lookup_id TEXT PRIMARY KEY, query TEXT NOT NULL, topic TEXT NOT NULL, "
    "status TEXT NOT NULL, sources JSONB NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_web_search_lookups_created "
    "ON web_search_lookups (created_at);"
)

# 話題新聞（spec 2026-07-20）：爬來的新聞暫存，供 proactive 問候當開場話題，
# 過期由排程清除（見 news/jobs.py）。news_item_id 為決定性 id（source_id＋url 雜湊，
# 見 news/fetchers/_ids.py），同一篇文章重複爬到會 upsert 而非重複插入。
NEWS_ITEMS_DDL = (
    "CREATE TABLE IF NOT EXISTS news_items ("
    "news_item_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, title TEXT NOT NULL, "
    "url TEXT NOT NULL, publisher TEXT NOT NULL, content TEXT NOT NULL, "
    "published_at DOUBLE PRECISION, retrieved_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_news_items_retrieved ON news_items (retrieved_at);"
)

# 新聞提及紀錄（D-74 消費端，2026-07-25）：get_news 給過哪位長輩哪則新聞，
# 供不重複給料；同一（長輩, 新聞）只留一列，逾期與 news_items 同步清除。
NEWS_MENTIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS news_mentions ("
    "elder_id TEXT NOT NULL, news_item_id TEXT NOT NULL, "
    "mentioned_at DOUBLE PRECISION NOT NULL, "
    "PRIMARY KEY (elder_id, news_item_id));"
)

# 長輩客製化聲音複製設定檔（聲音克隆，2026-07-30）：一位長輩最多一組「目前生效」的
# 參考語音，PK 直接用 elder_id；revoked_at 非 NULL 視同無效，同 consents 表慣例。
VOICE_PROFILES_DDL = (
    "CREATE TABLE IF NOT EXISTS voice_profiles ("
    "elder_id TEXT PRIMARY KEY, "
    "prompt_audio_url TEXT NOT NULL, "
    "prompt_text TEXT NOT NULL, "
    "consented_by TEXT NOT NULL, "
    "granted_at DOUBLE PRECISION NOT NULL, "
    "revoked_at DOUBLE PRECISION);"
)

# 觀測五表以 external_id＋channel 記來源（✅ 庚-07／A-8）：欄位承載任一通道的外部
# 識別碼（非僅 LINE），故正名為 external_id 並加 channel 標明來源通道。
#
# ⚠️ 建表與建索引「必須」拆成兩段常數，中間夾 OBSERVABILITY_EXTERNAL_ID_MIGRATION_DDL
# （見 ensure_schema）。既有庫的表早已存在，CREATE TABLE IF NOT EXISTS 對它是 no-op、
# 不會生出 external_id；若索引緊接著建，就會在還叫 line_user_id 的舊表上找不到欄位而
# 炸 UndefinedColumn。順序必須是：建表 → 改名遷移 → 建索引。
OBSERVABILITY_TABLES_DDL = (
    "CREATE TABLE IF NOT EXISTS webhook_events ("
    "webhook_event_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, "
    "external_id TEXT NOT NULL, channel TEXT NOT NULL DEFAULT '', "
    "event_type TEXT NOT NULL, message_type TEXT NOT NULL, "
    "payload JSONB NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE TABLE IF NOT EXISTS asr_calls ("
    "asr_call_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, external_id TEXT NOT NULL, "
    "channel TEXT NOT NULL DEFAULT '', "
    "status TEXT NOT NULL, latency_ms INTEGER NOT NULL, transcript TEXT NOT NULL, "
    "source_audio_url TEXT NOT NULL, error_message TEXT NOT NULL, "
    "created_at DOUBLE PRECISION NOT NULL);"
    "CREATE TABLE IF NOT EXISTS llm_calls ("
    "llm_call_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, external_id TEXT NOT NULL, "
    "channel TEXT NOT NULL DEFAULT '', "
    "status TEXT NOT NULL, latency_ms INTEGER NOT NULL, model_name TEXT NOT NULL, "
    "input_tokens INTEGER, output_tokens INTEGER, content TEXT NOT NULL, "
    "error_message TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    # 呼叫種類（2026-07-25）：一輪多筆 LLM 呼叫且快慢差一個量級，不分種類做 p50／p95
    # 會把三種東西平均在一起（見 observability/models.py 的 LLM_CALL_KIND_*）。
    # 既有列補 ''＝加欄前的舊資料，統計時另歸 llm:unknown，不混入任何一類。
    "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT '';"
    "CREATE TABLE IF NOT EXISTS tts_calls ("
    "tts_call_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, external_id TEXT NOT NULL, "
    "channel TEXT NOT NULL DEFAULT '', "
    "status TEXT NOT NULL, latency_ms INTEGER NOT NULL, content TEXT NOT NULL, "
    "error_message TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE TABLE IF NOT EXISTS replies ("
    "reply_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, external_id TEXT NOT NULL, "
    "channel TEXT NOT NULL DEFAULT '', "
    "kind TEXT NOT NULL, status TEXT NOT NULL, latency_ms INTEGER NOT NULL, "
    "round_trip_ms INTEGER, audio_url TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "ALTER TABLE replies ADD COLUMN IF NOT EXISTS opik_trace_id TEXT NOT NULL DEFAULT '';"
    "CREATE TABLE IF NOT EXISTS rag_calls ("
    "rag_call_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, elder_id TEXT NOT NULL, "
    "query TEXT NOT NULL, index_version TEXT NOT NULL, status TEXT NOT NULL, "
    "latency_ms INTEGER NOT NULL, safety_level TEXT NOT NULL, reason TEXT NOT NULL, "
    "hits JSONB NOT NULL, citations JSONB NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
)

# 觀測六表索引：前五表須在改名遷移後才建；rag_calls 以 trace／created 索引。
OBSERVABILITY_INDEXES_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_webhook_events_trace ON webhook_events (trace_id);"
    "CREATE INDEX IF NOT EXISTS idx_webhook_events_created ON webhook_events (created_at);"
    "CREATE INDEX IF NOT EXISTS idx_asr_calls_trace ON asr_calls (trace_id);"
    "CREATE INDEX IF NOT EXISTS idx_asr_calls_external_created "
    "ON asr_calls (external_id, created_at);"
    "CREATE INDEX IF NOT EXISTS idx_llm_calls_trace ON llm_calls (trace_id);"
    "CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls (created_at);"
    "CREATE INDEX IF NOT EXISTS idx_tts_calls_trace ON tts_calls (trace_id);"
    "CREATE INDEX IF NOT EXISTS idx_tts_calls_created ON tts_calls (created_at);"
    "CREATE INDEX IF NOT EXISTS idx_replies_trace ON replies (trace_id);"
    "CREATE INDEX IF NOT EXISTS idx_replies_created ON replies (created_at);"
    "CREATE INDEX IF NOT EXISTS idx_rag_calls_trace ON rag_calls (trace_id);"
    "CREATE INDEX IF NOT EXISTS idx_rag_calls_created ON rag_calls (created_at);"
)

# 觀測五表欄位正名遷移（✅ 庚-07，冪等）：既有庫 line_user_id → external_id、補 channel。
# 以 DO 區塊守門：僅在仍有 line_user_id 且尚無 external_id 時改名；新庫 DDL 已直接建
# external_id，DO 區塊自動略過。channel 一律 ADD IF NOT EXISTS。
_OBSERVABILITY_TABLES = ("webhook_events", "asr_calls", "llm_calls", "tts_calls", "replies")
OBSERVABILITY_EXTERNAL_ID_MIGRATION_DDL = "".join(
    "DO $$ BEGIN "
    f"IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = '{t}' "
    "AND column_name = 'line_user_id') AND NOT EXISTS (SELECT 1 FROM "
    f"information_schema.columns WHERE table_name = '{t}' AND column_name = 'external_id') "
    f"THEN ALTER TABLE {t} RENAME COLUMN line_user_id TO external_id; END IF; END $$;"
    f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT '';"
    for t in _OBSERVABILITY_TABLES
) + (
    # 改名殘骸：RENAME COLUMN 會讓舊索引 idx_asr_calls_line_user_created 自動改指
    # external_id，定義與新建的 idx_asr_calls_external_created 完全相同——留著只是
    # 讓每次寫入多維護一份同內容的 btree。新庫沒有這個索引，IF EXISTS 自動略過。
    "DROP INDEX IF EXISTS idx_asr_calls_line_user_created;"
)

# risk_events 既有表補 trace_id（可空）：讓風險事件掛回該輪鏈路。
RISK_EVENTS_TRACE_MIGRATION_DDL = "ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS trace_id TEXT;"

# replies 既有表補 round_trip_ms（可空，✅ D-05 戊-2）：端到端往返延遲；NULL＝未量測。
REPLIES_ROUND_TRIP_MIGRATION_DDL = (
    "ALTER TABLE replies ADD COLUMN IF NOT EXISTS round_trip_ms INTEGER;"
)

# 會話主鍵遷移（冪等）：turns／risk_events／conversation_summaries 加 elder_id、
# 摘要卸下舊主鍵改掛 (elder_id, date) 部分唯一索引；line_user_id 死欄已於
# 遷移末段 DROP（✅ 庚-45——1B 證實孤兒列全為測試資料，Leo 核定收縮）。
SESSION_KEY_MIGRATION_DDL = (
    "ALTER TABLE turns ADD COLUMN IF NOT EXISTS elder_id TEXT;"
    "CREATE INDEX IF NOT EXISTS idx_turns_elder_created ON turns (elder_id, created_at);"
    "ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS elder_id TEXT;"
    "CREATE INDEX IF NOT EXISTS idx_risk_events_elder_created "
    "ON risk_events (elder_id, created_at);"
    "ALTER TABLE conversation_summaries ADD COLUMN IF NOT EXISTS elder_id TEXT;"
    "ALTER TABLE conversation_summaries DROP CONSTRAINT IF EXISTS conversation_summaries_pkey;"
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_summaries_elder_date "
    "ON conversation_summaries (elder_id, date) WHERE elder_id IS NOT NULL;"
    # 死欄收縮（✅ 庚-45／A-25、A-37；Leo 核定 DROP）：1B 已證實舊資料 100% 孤兒
    # 測試資料，觀測五表已於庚-07 正名——三表 line_user_id 僅剩混淆價值。
    "ALTER TABLE turns DROP COLUMN IF EXISTS line_user_id;"
    "ALTER TABLE risk_events DROP COLUMN IF EXISTS line_user_id;"
    "ALTER TABLE conversation_summaries DROP COLUMN IF EXISTS line_user_id;"
)

# 帳號欄位退役（收縮步，冪等）：LINE 識別已全面遷入 channel_bindings。
ACCOUNTS_LINE_COLUMNS_RETIRE_DDL = (
    "ALTER TABLE elders DROP COLUMN IF EXISTS line_user_id;"
    "ALTER TABLE guardians DROP COLUMN IF EXISTS line_user_id;"
)

# 死碼欄位退役（✅ 己-8，D-09）：家屬看逐字對話不開放，開關欄位無人讀取。
ELDER_GUARDIANS_TRANSCRIPT_COLUMN_RETIRE_DDL = (
    "ALTER TABLE elder_guardians DROP COLUMN IF EXISTS can_view_transcript;"
)

# 遷移用的交易級諮詢鎖鍵：webhook 與 scheduler 同時啟動時，讓 ensure_schema 的 DDL
# 串行化，避免併發跑遷移互搶 AccessExclusiveLock 造成 Postgres 死結。任意固定常數即可，
# 全專案共用同一把鎖。
SCHEMA_MIGRATION_LOCK_KEY = 4_242_001


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def ensure_schema(database_url: str) -> None:
    with connect(database_url) as conn:
        # 先搶交易級諮詢鎖再跑 DDL：webhook 與 scheduler 同時啟動時，讓兩者的遷移
        # 串行化（後到者等前一個 commit 後才進場，DDL 皆冪等等於接著 no-op），
        # 避免併發跑遷移互搶 AccessExclusiveLock 造成 Postgres 死結。鎖隨交易結束自動釋放。
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_MIGRATION_LOCK_KEY,))
        conn.execute(MEMORY_DDL)
        conn.execute(ACCOUNTS_DDL)
        conn.execute(CHANNEL_BINDINGS_DDL)
        conn.execute(APP_ACCOUNTS_DDL)
        conn.execute(BINDING_DDL)
        conn.execute(SCHEDULER_DDL)
        conn.execute(RATE_LIMIT_DDL)
        conn.execute(SCHEDULES_DDL)
        conn.execute(RAG_DDL)
        conn.execute(RISK_EVENTS_DDL)
        conn.execute(REMINDER_LOGS_DDL)
        conn.execute(STRATEGIES_DDL)
        conn.execute(GREETING_PREFERENCES_DDL)
        conn.execute(ELDER_LOCATIONS_DDL)
        conn.execute(ELDER_LOCATIONS_COORDS_MIGRATION_DDL)
        conn.execute(REMINDER_LOGS_RESPONDED_MIGRATION_DDL)
        conn.execute(RISK_NOTIFICATION_LOGS_DDL)
        conn.execute(APP_NOTIFICATIONS_DDL)
        conn.execute(WEB_SEARCH_LOOKUPS_DDL)
        conn.execute(MEMORY_CONSOLIDATIONS_DDL)
        conn.execute(CONVERSATION_SUMMARIES_DDL)
        conn.execute(NEWS_ITEMS_DDL)
        conn.execute(NEWS_MENTIONS_DDL)
        conn.execute(VOICE_PROFILES_DDL)
        # 三段順序不可調換：建表（既有庫 no-op）→ 舊欄改名／補 channel → 建索引。
        # 索引引用 external_id，既有庫要先改完名才建得起來。
        conn.execute(OBSERVABILITY_TABLES_DDL)
        conn.execute(OBSERVABILITY_EXTERNAL_ID_MIGRATION_DDL)
        conn.execute(OBSERVABILITY_INDEXES_DDL)
        conn.execute(RISK_EVENTS_TRACE_MIGRATION_DDL)
        conn.execute(REPLIES_ROUND_TRIP_MIGRATION_DDL)
        conn.execute(SESSION_KEY_MIGRATION_DDL)
        conn.execute(ACCOUNTS_LINE_COLUMNS_RETIRE_DDL)
        conn.execute(ELDER_GUARDIANS_TRANSCRIPT_COLUMN_RETIRE_DDL)
        # ⚠ 必須排在 SCHEDULES_DDL 之後：先確定新表在，再丟掉舊表。
        conn.execute(LEGACY_REMINDER_TABLES_RETIRE_DDL)
        conn.commit()


class StoreError(Exception):
    """資料庫存取失敗（連線／執行／交易）；各 store 會翻成自己的領域錯誤。"""


class Executor(Protocol):
    """可執行 SQL 的對象：Database 本身或交易內的單一連線。

    transaction() 宣告於此（✅ 庚-43／A-58）：_Errors 包裝時不再 type: ignore；
    交易內的 _ConnExecutor 不支援巢狀交易、呼叫即拋。"""

    def execute(self, sql: str, params: tuple = ()) -> None: ...
    def query(self, sql: str, params: tuple = ()) -> list[tuple]: ...
    def query_one(self, sql: str, params: tuple = ()) -> tuple | None: ...
    def transaction(self) -> object: ...


class _ConnExecutor:
    """包一條交易連線並提供 Executor 介面（不自行 commit；交易結束統一提交）。"""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()) -> None:
        self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self._conn.execute(sql, params).fetchall()

    def transaction(self):  # pragma: no cover - 防呆
        raise StoreError("交易內不支援巢狀交易")

    def query_one(self, sql: str, params: tuple = ()) -> tuple | None:
        return self._conn.execute(sql, params).fetchone()


class Database:
    """連線池 ＋ 交易 ＋ 錯誤翻譯。所有方法失敗丟 StoreError。"""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @classmethod
    def open(cls, url: str, *, min_size: int = 1, max_size: int = 5) -> Database:
        return cls(ConnectionPool(url, min_size=min_size, max_size=max_size, open=True))

    def close(self) -> None:
        self._pool.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(sql, params)
                conn.commit()
        except StoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - 一律翻成 StoreError
            raise StoreError(str(exc)) from exc

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        try:
            with self._pool.connection() as conn:
                return conn.execute(sql, params).fetchall()
        except StoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StoreError(str(exc)) from exc

    def query_one(self, sql: str, params: tuple = ()) -> tuple | None:
        try:
            with self._pool.connection() as conn:
                return conn.execute(sql, params).fetchone()
        except StoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StoreError(str(exc)) from exc

    @contextmanager
    def transaction(self) -> Iterator[Executor]:
        # 只翻譯 DB 層錯誤（psycopg；連線池例外亦繼承之）。交易本體（yield 區段）
        # 拋出的業務例外（如 InviteError）原樣穿透——回滾照常發生，但不得被
        # 誤包成 StoreError（會再被 _Errors 翻成領域錯誤，呼叫端就接不到了）。
        try:
            with self._pool.connection() as conn, conn.transaction():
                yield _ConnExecutor(conn)
        except StoreError:
            raise
        except psycopg.Error as exc:
            raise StoreError(str(exc)) from exc


class _Errors:
    """把內層 Executor 丟的 StoreError 翻成某 store 的領域錯誤；本身也是 Executor。"""

    def __init__(self, inner: Executor, wrap: Callable[[str], Exception]) -> None:
        self._inner = inner
        self._wrap = wrap

    def execute(self, sql: str, params: tuple = ()) -> None:
        try:
            self._inner.execute(sql, params)
        except StoreError as exc:
            raise self._wrap(str(exc)) from exc

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        try:
            return self._inner.query(sql, params)
        except StoreError as exc:
            raise self._wrap(str(exc)) from exc

    def query_one(self, sql: str, params: tuple = ()) -> tuple | None:
        try:
            return self._inner.query_one(sql, params)
        except StoreError as exc:
            raise self._wrap(str(exc)) from exc

    @contextmanager
    def transaction(self) -> Iterator[Executor]:
        try:
            # _Errors 只用來包 Database（有 transaction()）；Executor Protocol 僅涵蓋三個基本操作
            with self._inner.transaction() as tx:
                yield _Errors(tx, self._wrap)
        except StoreError as exc:
            raise self._wrap(str(exc)) from exc
