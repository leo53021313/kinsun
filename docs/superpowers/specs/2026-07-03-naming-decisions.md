# 命名決策表（2026-07-03）

> 核可方式：回覆「全部照建議」，或指定「#N 改成 xxx」「#N 不改」。
> 「決議」欄由使用者核可後填入；未填「核可」的列一律不動。
> 「建議＝不改」的列是盤點中判定現況合理、但需要你知情確認的項目。

## 一、程式識別字

| # | 概念 | 現況寫法（處數） | 建議 | 理由 | 影響範圍 | 決議 |
|---|------|------------------|------|------|----------|------|
| 1 | LINE 平台使用者 ID | `session_id`(195)／`line_user_id`(113)／`user_id`(63)／`line`(53, binding 內部)／`line_id`(6)／`elder_line_id`(4) | 統一 **`line_user_id`** | 同一顆值六種名字（notifier.py 一檔就有四種）；`session_id` 誤導（存的就是 LINE ID，docstring 自己承認）；accounts 層已用 line_user_id 且語意最準 | src＋tests 全域；DB 欄位見 #28 | （待核可） |
| 2 | `elder_id`（長輩業務主鍵，385 處） | 與 #1 是**不同概念**（uuid 合成主鍵 vs 外部平台 ID） | **維持不同名、不合併** | 合併會讓業務實體與平台帳號混淆；Pusher 的收件者也可能是家屬 | 無改動 | （待核可） |
| 3 | 資料存取層類別 | `*Store`(19 類)／`*Repository`(2 類, 僅 accounts) | 統一 **`Store`**（`AccountRepository`→`AccountStore`、`PgAccountRepository`→`PgAccountStore`、`FakeAccountRepository`→`FakeAccountStore`） | 9:1 壓倒性主流，改動面最小；docstring 連中文都自稱「儲存層」 | 64 處／17 檔；檔名連動 #17 | （待核可） |
| 4 | Upsert 動詞 | `save/save_*`(12)／`add`(4)／`upsert`(2) | 統一 **`save`**（`add`→`save`、`upsert`→`save`；`set_last_run` 維持——key-value 語意清楚） | 全是 `ON CONFLICT DO UPDATE` 同語意；`add` 誤導呼叫端以為純新增會撞鍵 | appointment/medication store＋service、reports/summaries | （待核可） |
| 5 | 刪除動詞 | `remove`(Service/Store, 6)／`delete`(API handler, 2) | **不改**（分層慣例：HTTP 層 delete 對應 REST 動詞、內部層 remove） | 屬合理分層選字，強改收益低 | 無改動；規範記錄 | （待核可） |
| 6 | API handler 建立動詞 | `create_elder` vs `add_medication`／`add_appointment` | 統一 **`create_*`**（`add_medication`→`create_medication`、`add_appointment`→`create_appointment`） | 同為 POST 建立資源回 201；與 `CreateElderIn` 模型呼應 | web/api.py 3 個函式名（不動路由路徑） | （待核可） |
| 7 | 「已同意」判斷式 | `is_consented_elder`(12)／`is_consented`(9, jobs 形參) | 統一 **`is_consented_elder`** | 同一個函式跨層被改名（scheduler 直接把 `accounts.is_consented_elder` 傳進叫 `is_consented` 的形參） | medication/appointment jobs＋scheduler/worker＋tests | （待核可） |

## 二、環境變數與設定

| # | 鍵 | 現況 | 建議 | 理由 | 影響範圍 | 決議 |
|---|----|------|------|------|----------|------|
| 8 | `LLM_TIMEOUT_SECONDS` | 孤兒鍵（.env.example 未列），且同一 Gemini client 的其他鍵都用 `GEMINI_` 前綴 | 改 **`GEMINI_TIMEOUT_SECONDS`**（`Settings.llm_timeout_seconds`→`gemini_timeout_seconds`）並補進 .env.example | 同一物件的設定共享同一前綴 | config.py、app.py、scheduler/worker.py、.env.example、實際 .env | （待核可） |
| 9 | `ASR_TIMEOUT_SECONDS` | 孤兒鍵（程式有讀、.env.example 未列；對稱的 TTS_TIMEOUT_SECONDS 有列） | **名稱不變，補列 .env.example**（`ASR_TIMEOUT_SECONDS=15`） | 收錄對稱性 | .env.example | （待核可） |
| 10 | `CONSOLIDATION_HOUR` | 無前綴（同組 SCHEDULER_TICK_SECONDS 有前綴） | 改 **`LONGTERM_CONSOLIDATION_HOUR`** | 業務歸屬是 longterm 模組（consolidation.py 直接取用），與既有 LONGTERM_TOP_K 對齊 | config.py、worker.py、.env.example、docs、實際 .env | （待核可） |
| 11 | `GREETING_HOUR`／`INACTIVITY_HOUR`／`INACTIVITY_DAYS` | 無前綴 | 改 **`PROACTIVE_GREETING_HOUR`／`PROACTIVE_INACTIVITY_HOUR`／`PROACTIVE_INACTIVITY_DAYS`** | 三者屬主動關懷（proactive 模組）語意群組 | 同 #10 | （待核可） |
| 12 | `EMBEDDING_MODEL` | 無前綴（同屬長期記憶的 LONGTERM_TOP_K 有前綴） | 改 **`LONGTERM_EMBEDDING_MODEL`** | 泛名易被誤認為全域設定；與子系統前綴對齊 | config.py、mem0_factory.py、.env.example、實際 .env | （待核可） |
| 13 | `DEBUG_SHOW_TRANSCRIPT` | 全專案唯一 `DEBUG_` 開頭鍵 | 改 **`ASR_DEBUG_SHOW_TRANSCRIPT`** | 語意屬 ASR／語音回覆管線，避免看似全域 debug 開關 | config.py、app.py、.env.example、實際 .env | （待核可） |
| 14 | `LIFF_ID` | richmenu.py CLI 裸讀 os.environ，不經 config.py | **不改名**；.env.example 加註「僅供 richmenu CLI 讀取，不經 config.py」 | 收進 Settings 需連帶必填項耦合，超出改名範疇 | .env.example 註解 | （待核可） |
| 15 | `KINSUN_IT`、`SUPABASE_*`／`AUDIO_*`、`NGROK_*`、services 端 env 歸屬 | 分組與前綴規則只存在於作者習慣 | **不改名**；規則文件化入 AGENTS.md 與 .env.example 註解（KINSUN_ 前綴保留給測試旗標；SUPABASE_ 為專案憑證層；DGX 服務端 env 見 services/*/README） | 把巧合變成規則 | Task 10 文件 | （待核可） |

## 三、檔案與模組命名

| # | 涉及路徑 | 現況 | 建議 | 理由 | 影響範圍 | 決議 |
|---|----------|------|------|------|----------|------|
| 16 | `src/kinsun/rag/schemas.py` | 唯一叫 schemas 的領域模型檔（其餘三個模組都叫 models.py） | 改 **`rag/models.py`** | 角色與 accounts/appointment/medication 的 models.py 完全相同 | import 12 處／11 檔 | （待核可） |
| 17 | `src/kinsun/accounts/repository.py` | 唯一叫 repository 的持久層檔 | 改 **`accounts/store.py`**（連動 #3 類別名；`tests/test_pg_account_repository.py`→`test_pg_accounts_store.py`） | 與其餘 9 個持久層檔名對齊 | import 6 處＋#3 的 64 處 | （待核可） |
| 18 | `src/kinsun/appointment/`、`src/kinsun/medication/` | 單數目錄（accounts/channels/reports/tools 皆複數；API 路由、前端頁面、測試檔名也都用複數） | 改 **`appointments/`、`medications/`**（12 支測試檔名連動改複數） | 目錄代表實體集合，全庫僅這兩個落後 | import 31＋38 處＋測試檔名 12 支 | （待核可） |
| 19 | `src/kinsun/longterm/` | 雙字連寫 | **不改**（全庫無其他雙字詞目錄可比對，不違反現行風格） | 改動 16 處 import 收益低 | 無改動 | （待核可） |
| 20 | tests/ 檔名與被測模組對應 | 11 支測試檔缺套件前綴或用類別名命名 | 統一 **`test_<套件>_<檔>.py`**：test_database→test_db、test_memory_context→test_recall、test_risk_events→test_safety_events、test_reminder_logs→test_reminders、test_fanout→test_scheduler_fanout、test_weather_tool→test_tools_weather、test_asr→test_speech_asr、test_tts→test_speech_tts、test_inbound→test_channels_inbound、test_richmenu→test_line_richmenu、test_webhook→test_line_webhook | 同套件多數檔已遵循此規則，僅個別漏掉 | 純檔名（無 import 引用） | （待核可） |
| 21 | 整合測試組織 | 「同檔內 KINSUN_IT skip」與「獨立 test_pg_*.py」兩策略並存 | **本次不搬內容**；慣例（新整合測試獨立 test_pg_*.py）記入規範 | 搬移測試內容屬重構，超出改名範疇 | Task 10 文件 | （待核可） |
| 22 | `frontend/src/meds.ts` | 全案唯一縮寫檔名 | 改 **`medicationSlots.ts`**（內容實為用藥時段標籤工具，取精確名優於僅去縮寫） | 與前後端 medication 全字慣例對齊 | import 1 處 | （待核可） |
| 23 | `frontend/src/report.ts` | 命名稍籠統 | **不改**（現無其他 report 概念混淆） | 改動收益低 | 無改動 | （待核可） |

## 四、API 路由與欄位

| # | 端點／欄位 | 現況 | 建議 | 理由 | 前端同步處 | 決議 |
|---|-----------|------|------|------|-----------|------|
| 24 | `med_id`／`appt_id`（路徑參數＋JSON 欄位＋domain model 欄位） | elder 全字但 medication/appointment 縮寫；`kind` 值卻用全字 "medication"/"appointment" | 統一 **`medication_id`／`appointment_id`**（DB 欄位連動 #29） | 縮寫規則不存在，同資源全字／縮寫並存需記兩套詞彙 | api.ts 型別與路徑、MedicationsPage、AppointmentsPage | （待核可） |
| 25 | `POST /api/elders` 請求 `elder_name` | request 用 `elder_name`、response 用 `name`（同一實體同一端點兩個鍵） | request 改 **`name`**（`guardian_name` 維持——不同人） | 消除前端手動橋接兩套 key | api.ts createElder、EldersPage | （待核可） |
| 26 | health-report 內部查詢鍵 | risk_events 用 `session_id`、reminders 用 `elder_id` 查，同端點兩套語意 | 隨 **#1／#28** 統一為 `line_user_id`（RiskEventStore 介面連動） | 同 #1 | 前端無感（wire format 不變） | （待核可） |
| 27 | `/health-report`（單數）vs `/guardian-invites`（複數） | 單複數規則未文件化 | **不改**；規則（聚合物件單數、可建多筆集合複數）記入規範 | 有 REST 理論依據，改動屬破壞性且收益低 | Task 10 文件 | （待核可） |

## 五、DB Schema

| # | 表／欄位 | 現況 | 建議 | 理由 | 影響 SQL 數 | 決議 |
|---|----------|------|------|------|-------------|------|
| 28 | `turns.session_id`、`risk_events.session_id`、`conversation_summaries.session_id` | 存的值是 LINE user ID，卻叫 session_id；同一長輩在 schema 中三種欄位名 | 改 **`line_user_id`**（#1 的 DB 面；不改存 elder_id——那是行為變更非改名） | 如實反映值語意，與 elders.line_user_id 可直接對應 | 14 條 | （待核可） |
| 29 | `medications.med_id`、`appointments.appt_id`、`risk_events.event_id`、`reminder_logs.log_id` | 主鍵縮寫或省略表名前綴（elders.elder_id、guardians.guardian_id 為全稱慣例） | 改 **`medication_id`／`appointment_id`／`risk_event_id`／`reminder_log_id`**（與 #24 連動） | `<表單數>_id` 是本 schema 多數慣例 | 16 條 | （待核可） |
| 30 | `turns.id`（BIGSERIAL） | 全庫唯一自增數字主鍵 | **不改**（高頻寫入對話紀錄用自增鍵是刻意技術選型） | 合理設計差異 | 無改動 | （待核可） |
| 31 | `turns.text` vs `reminder_logs.content`、`conversation_summaries.content` | 同為「一段文字內容」兩種名 | 統一 **`content`**（turns.text→content；`Message.text`→`Message.content` 連動——role/content 也是聊天訊息業界慣例） | 無語意差異可解釋異名 | 10 條＋llm.py/agent.py 引用 | （待核可） |
| 32 | `appointments.appt_date` vs model `Appointment.date` | DB 與程式模型異名，靠位置對應維持正確 | DB 欄位改 **`date`**（與模型及 conversation_summaries.date 對齊） | 消除 DB／程式落差；目前 positional unpacking 脆弱 | 5 條 | （待核可） |
| 33 | `scheduler_state`（單數表名） | 全庫唯一單數表 | **不改**（key-value 狀態表非多筆紀錄語意）；規範記錄 | 合理例外 | 無改動 | （待核可） |

## 附錄 A：判定一致、無需改動（知情即可，不需決議）

- 時間戳欄位一律 `<動詞>_at` ＋ DOUBLE PRECISION epoch（9 欄全一致）。
- `config.py` 欄位名＝環境變數小寫，映射規則 100% 一致（將寫入規範作為強制慣例）。
- 查詢動詞分工（get 單筆／list_for_* 清單／query 原生 SQL／search 檢索／load 外部內容）無衝突。
- `jobs.py` 分散於四個領域目錄是刻意慣例（角色、命名皆一致）。
- `services/asr|tts` 與 `speech/asr|tts.py` 跨層同名合理（伺服器 vs client）。
- `scheduler/scheduler.py` 套件核心引擎命名模式合理。
- reports/safety/binding 未拆三層檔屬合理精簡。
- `role` 欄位三表同名不同義，作用域獨立可接受。
- natural key（invites.code、binding_sessions.line_user_id、scheduler_state.job_name）設計合理。
- `RICH_MENU_ID` 不掛 LIFF_ 前綴語意正確（LINE 平台資源非 LIFF 屬性）。
- `LIFF_CHANNEL_ID` 與 `LIFF_ID` 概念本不同（Login channel vs LIFF app），維持現名。

## 附錄 B：盤點附帶發現（非命名問題，本次不動，供日後參考）

- `*_PRELOAD` 布林解析不一致：TTS_PRELOAD 把空字串視為假、ASR_PRELOAD 不會；三處 inline 實作未共用 _parse_bool。建議另開小修。
- `appointment/models.py` 無對應測試（兄弟模組 medication 有）；`app.py`、`scheduler/worker.py`、`channels/line/messenger.py` 無直接測試。
- `richmenu.py` 裸讀的兩個鍵名字面量未與 config.py 集中，改名時易漏。
- `.env.example` 與 `frontend/.env.example` 應互相加註 `LIFF_ID`＝`VITE_LIFF_ID` 需同值（隨 #14 一併補註解）。

## 附錄 C：需人工同步的項目（核可後生效）

- 本機與 DGX 實際 `.env`（不在版控）：#8、#10、#11、#12、#13 若核可，需手動同步改鍵（舊名 → 新名清單將於批次四完成後更新於此）。
- Supabase／Postgres 開發庫：#28、#29、#31、#32 若核可，開發庫直接重建（資料可丟，無遷移）。
