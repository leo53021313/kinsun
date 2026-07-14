# Agent 自我進化：每晚反思與策略記憶 設計文件

- 日期：2026-07-14
- 狀態：設計已由 Leo 核可，待實作
- 相關決策：只做第一層（個人化偏好）、訊號用「逐字稿＋行為訊號」、守則先人審後自動、固定上限 15 條汰換制、每晚自動反思（非手動觸發）

## 背景與動機

金孫目前**沒有任何自我進化能力**。系統會累積「關於長輩的事實」（Mem0 長期記憶、RAG 知識庫），但不會累積「關於自己怎麼做得更好」的知識。所有 prompt 都是硬寫死的常數，所有成效資料（`risk_events`、`reminder_logs`、`llm_calls`）的終點都是 `/admin` 給人看，沒有一條線回到系統自己的決策。

具體痛點：金孫不會發現「這位長輩早上八點還在睡，問候該改七點半」「這位長輩不愛被叫阿婆」「講太長她就不回了」。每天重複同樣的失誤，靠人去改 code 才會變好。

業界（Hermes、OpenClaw）的「自我進化」本質是：**把互動中學到的教訓寫成文字，下次自動讀回 context**。不是重訓模型。本設計採同一路線的最小可行版本。

### 範圍界定

進化分三層，本設計**只做第一層**：

| 層 | 內容 | 本次 |
| :--- | :--- | :--- |
| 一 | 個人化偏好（稱呼、語氣、作息、話題） | ✅ 做 |
| 二 | 規則參數自動校正（危急門檻、關鍵詞表） | ❌ 不做 |
| 三 | Prompt／工具自我改寫（版本化、GEPA 最佳化） | ❌ 不做 |

## 方案選擇

| 方案 | 說明 | 結論 |
| :--- | :--- | :--- |
| A：新增 `strategies/` 領域，走既有三件套＋`FactProvider` 注入 | 守則是獨立領域概念，有自己的生命週期；沿用 `MedicationFacts`／`AppointmentFacts` 的注入模式 | ✅ 採用 |
| B：守則塞進 Mem0 長期記憶，用 metadata 分流 | Mem0 是向量檢索（依當下問題撈），守則需每輪全取；且守則要有待審／採用狀態與人審介面，Mem0 無處可放。兩種語意混一起，日後拆不開 | ❌ |
| C：直接做 prompt 版本化 | 屬第三層，超出本次範圍 | ❌ |

## 閉環設計

```
長輩互動 ──→ 訊號落庫（turns / reminder_logs.responded_at）
                      │
                      ↓ 每晚自動（掛既有夜間批次）
              反思 reflect_day(elder_id)
                      │
                      ↓ 一律 status=pending
              候選守則寫入 strategies 表
                      │
                      ↓ Leo 在 /admin 逐條採用或丟棄
              status=adopted
                      │
                      ↓ 每輪對話自動注入
              StrategyFacts → FactSection → system prompt
                      │
                      ↓
              行為改變 ──→ 產生新的訊號（回到起點）
```

四個零件對到程式碼：

1. **訊號**：`turns`（逐字稿，已有）＋ `reminder_logs.responded_at`（新增）
2. **反思**：`strategies/reflection.py` 的 `reflect_day()`，掛進 `scheduler/worker.py:71` 的 `run_one()`
3. **回注**：`strategies/facts.py` 的 `StrategyFacts`，掛進 `composition.py:149` 的 `SessionMemory(facts=[...])`
4. **守門**：候選守則一律 `pending`；`/admin/strategies` 人審後才生效

**核心優勢：`agent.py` 一個字都不用改。** 注入走既有的 `FactProvider` 協定（`memory/recall.py:16`），排版走既有的 `format_injected_context`（`memory/models.py:65`）。

## 元件設計

### 1. 資料模型：`src/kinsun/strategies/models.py`

```python
@dataclass(frozen=True)
class Strategy:
    strategy_id: str
    elder_id: str
    content: str                        # 一句話的守則本身
    category: str                       # ∈ STRATEGY_CATEGORIES
    evidence: str                       # 反思當下引用的證據（人審時看這欄）
    status: str                         # ∈ STRATEGY_STATUSES
    supersedes_strategy_id: str | None  # 這條取代哪一條舊的
    created_at: float
    reviewed_at: float | None
```

分類集中列舉（仿 `reports/reminders.py` 的 `REMINDER_KINDS`）：

```python
STRATEGY_CATEGORY_ADDRESS = "address"    # 稱呼：不愛被叫阿婆
STRATEGY_CATEGORY_TONE = "tone"          # 語氣：講太長會沒反應
STRATEGY_CATEGORY_ROUTINE = "routine"    # 作息：早上八點還在睡
STRATEGY_CATEGORY_TOPIC = "topic"        # 話題：不愛聊孫子
STRATEGY_CATEGORIES = (ADDRESS, TONE, ROUTINE, TOPIC)
```

`category` 欄位是**為第二階段「某類守則轉自動生效」預留**的維度：日後統計「作息類守則你幾乎都按採用」，就能把該類改為自動。第一版不使用此邏輯，只儲存。

狀態：

```python
STRATEGY_STATUS_PENDING = "pending"        # 反思產出，待人審
STRATEGY_STATUS_ADOPTED = "adopted"        # 已採用，會注入 prompt
STRATEGY_STATUS_REJECTED = "rejected"      # 人工丟棄
STRATEGY_STATUS_SUPERSEDED = "superseded"  # 被新守則取代
STRATEGY_STATUSES = (PENDING, ADOPTED, REJECTED, SUPERSEDED)
```

### 2. 持久層：`src/kinsun/strategies/store.py`（三件套）

```python
class StrategyStore(Protocol):
    def record(self, elder_id: str, content: str, category: str,
               evidence: str, supersedes_strategy_id: str | None) -> None: ...
    def list_for_elder(self, elder_id: str, *, status: str | None = None) -> list[Strategy]: ...
    def list_for_status(self, status: str) -> list[Strategy]: ...
    def adopt(self, strategy_id: str) -> None: ...
    def reject(self, strategy_id: str) -> None: ...
```

- `record` 為 append-only 事件語意（新守則永遠是新一筆），符合命名規範的 `record` 動詞慣例。
- `list_for_elder` 供反思與 `StrategyFacts` 使用（單一長輩）；`list_for_status` 供後台待審清單使用（**跨長輩**，依 `created_at` 由新到舊）。兩個查詢維度不同，故分兩個方法（命名依 `list_for_<維度>` 慣例）。
- `adopt` 在**同一個交易**內完成兩件事：把該筆設為 `adopted`＋若其 `supersedes_strategy_id` 非空，把被取代的那筆設為 `superseded`。此原子性是 15 條上限不被突破的保證。
- `PgStrategyStore` / `FakeStrategyStore` 同住 `store.py`（三件套規範）。

### 3. 反思：`src/kinsun/strategies/reflection.py`

```python
def reflect_day(
    elder_id: str, *, short_term, reminder_logs, strategies: StrategyStore,
    reflector, clock, max_strategies: int,
) -> None:
```

流程（樣板取自 `reports/summaries.py:104` 的 `summarize_day`）：

1. `turns = short_term.previous_day(elder_id)`，空則 return（沿用既有的凌晨盲窗解法）
2. 取同一天的提醒紀錄（含有無回應）：`reminder_logs.list_for_range(elder_id, start, end)`，時間界線用既有的 `previous_day_bounds(clock())`
3. 取目前已採用的守則：`strategies.list_for_elder(elder_id, status="adopted")`
4. 組 `REFLECTION_PROMPT`，呼叫 LLM，要求回傳 JSON 陣列
5. 解析、過濾（見下）、逐條 `strategies.record(...)`（一律 `pending`）

**餵給模型的第三樣（已採用守則）是關鍵**：有它，模型才能判斷「這條我早就知道」（不重複產出）與「這條跟舊的矛盾」（提出取代）。

**用哪顆模型**：沿用 `GEMINI_MODEL_SUMMARY`（與家屬摘要同一顆）。`worker.py:53-57` 已依此設定建好連線並在與主模型相同時共用，反思直接複用該 `gemini` 實例，**不新增模型設定**。

**15 條上限用「取代」維持**：prompt 明確告知目前已有幾條、上限 15；若已達上限且模型認為新守則更重要，**必須**在 `supersedes` 欄指定要頂掉哪一條的 `strategy_id`，否則該候選會被丟棄。prompt 長度因此是硬上限，不隨時間膨脹。

### 4. 安全紅線（不可協商）

照護場域的自我進化，錯誤代價與寫程式助理不同量級。三道防線：

1. **反思 prompt 明文禁止**：不得產出任何涉及用藥、劑量、就醫決策、危急判斷的守則；只能學相處風格（稱呼、語氣、作息、話題）。
2. **產出過濾**：解析後逐條過關鍵詞黑名單（沿用 `rag/answer_policy.py:19` 的 `_MEDICAL_ACTION_TERMS` 概念，`strategies/` 自帶一份），命中即丟棄並記 warning。
3. **注入時的段首警語**：`StrategyFacts` 產生的 `FactSection.title` 明載「以下是與這位長者的相處風格偏好，**不得凌駕安全提醒與用藥提醒**」。

金孫可以學會不叫長輩阿婆，但永遠不准學會不提醒她吃藥。

### 5. 回注：`src/kinsun/strategies/facts.py`

```python
class StrategyFacts:
    """FactProvider 實作：把已採用的守則排版成 FactSection 注入 system prompt。"""
    def facts(self, elder_id: str) -> FactSection | None: ...
```

- 只撈 `status='adopted'`，依 `created_at` 由新到舊取前 `max_strategies`（15）條。
- 無守則時回 `None`（`recall.py:57` 已處理 None）。
- 掛進 `composition.py:152` 的 `facts=[MedicationFacts(...), AppointmentFacts(...), StrategyFacts(...)]`。
- `recall.py:52-56` 的 per-provider try/except 已保證：守則讀取失敗**不會中斷對話**。

### 6. 行為訊號：`reminder_logs.responded_at`

`reports/reminders.py` 現況只記「我推了什麼」（`kind`／`content`／`created_at`），完全沒有「長輩有沒有理我」。新增：

- 資料表加 `responded_at DOUBLE PRECISION NULL`。
- `ReminderLog` dataclass 加對應欄位。
- `ReminderLogStore` 加兩個方法：
  - `mark_responded(elder_id: str, *, within_seconds: int) -> None`：把該長輩最近一則 `responded_at IS NULL` 且 `created_at` 在時間窗內的提醒標記為已回應。
  - `list_for_range(elder_id: str, *, start: float, end: float) -> list[ReminderLog]`：供反思讀當天提醒（命名對齊 `MemoryStore.list_for_range`）。
- 呼叫點：`pipeline.py` 處理長輩進站訊息時呼叫 `mark_responded`，失敗不影響對話（沿用 `safe_record` 的容錯慣例）。

**判定刻意做笨的**：只用 60 分鐘時間窗，**不做內容比對**。比對「這句是不是在回剛剛那則提醒」極易誤判，而反思只需要粗略的回應率訊號，不需要精準。YAGNI。

### 7. 人審介面

- `GET /admin/strategies?status=pending`：待審清單（顯示 content／category／evidence／要取代誰）。
- `PATCH /admin/strategies/{strategy_id}`：body `{"action": "adopt" | "reject"}`。

第一版只做後台，不做家屬端 UI（App 仍在地基階段）。

## 排程：每晚自動，非手動觸發

反思掛進 `scheduler/worker.py:71` 的 `run_one(elder_id)`，成為第三步：

```python
def run_one(elder_id: str) -> None:
    run_consolidation(...)      # 既有：長期記憶整理
    try: summarize_day(...)     # 既有：家屬摘要
    except: logger.warning(...)
    if settings.reflection_enabled:
        try: reflect_day(...)   # 新增：每晚反思
        except: logger.warning("反思失敗 elder=%s", elder_id)
```

`run_one` 由 `build_consolidation_job`（`scheduler/jobs.py`）驅動，**該 job 本來就是每晚 cron 自動執行**（`LONGTERM_CONSOLIDATION_HOUR` 的 xx:05）。因此反思是自動的主線行為；`/admin` 的手動觸發只是附帶能力（admin 遍歷同一份 jobs 清單，自動就有）。

不新增 cron、不新增 worker。

## 錯誤處理

一律不擴散，沿用 `run_one()` 既有慣例：

| 失敗情境 | 處理 |
| :--- | :--- |
| LLM 呼叫失敗 | 記 warning，跳過該長輩的反思；不影響整理、摘要、其他長輩 |
| 回傳非合法 JSON／欄位缺漏 | 記 warning，整批丟棄，不寫入任何守則 |
| 候選守則命中醫療詞黑名單 | 丟棄該條（其餘照寫），記 warning |
| 已達 15 條上限但未指定 supersedes | 丟棄該條，記 warning |
| `strategies` 讀取失敗（對話中） | `recall.py:52-56` 已 catch，該段略過，對話照常 |
| `mark_responded` 失敗 | 記 warning，不影響對話 |

## 設定（環境變數）

新子系統前綴 `REFLECTION_`，需補進 `.env.example` 與 `AGENTS.md` 命名表：

| 鍵 | 預設 | 說明 |
| :--- | :--- | :--- |
| `REFLECTION_ENABLED` | `true` | **緊急關閉開關**，非選配。反思為每晚自動主線行為；此旗標僅供反思行為異常時緊急停用 |
| `REFLECTION_MAX_STRATEGIES` | `15` | 每位長輩生效中的守則上限，同時是注入 prompt 的條數上限 |
| `REFLECTION_RESPONSE_WINDOW_MINUTES` | `60` | 提醒發出後多久內長輩有發言即算「已回應」 |

`Settings` 欄位名＝環境變數鍵小寫，一一對應（`reflection_enabled` 等）。

## 資料庫遷移

**必須測「既有庫升級」路徑**——空的測試庫測不到舊表加欄位的狀況。順序固定：

1. 建表 `strategies`
2. 遷移：`reminder_logs` ADD COLUMN `responded_at DOUBLE PRECISION`（可為 NULL，既有列自動為 NULL＝未回應，語意正確）
3. 建索引：`strategies(elder_id, status)`、`reminder_logs(elder_id, responded_at)`

## 測試策略（TDD，先寫測試）

| 測試檔 | 內容 |
| :--- | :--- |
| `test_strategies_store_contract.py` | 同一份斷言參數化跑 `FakeStrategyStore`（離線）與 `PgStrategyStore`（`KINSUN_IT=1`）：record／list_for_elder(status)／adopt 的取代原子性／reject |
| `test_strategies_reflection.py` | 假 summarizer 餵固定 JSON：格式正確→寫入 pending；格式壞掉→不寫入；含用藥詞→被擋；已滿 15 條未指定 supersedes→丟棄 |
| `test_strategies_facts.py` | 只回 adopted；超過上限只取前 15；無守則回 None；段首警語存在 |
| `test_reports_reminders.py` | 補 `mark_responded`（時間窗內／外）與 `list_for_range` |
| `test_pipeline.py` | 長輩進站訊息會呼叫 `mark_responded`；該呼叫失敗不影響回覆 |
| `test_pg_strategies_store.py` | Postgres 整合測試（`KINSUN_IT=1`） |

覆蓋率目標 80%＋（專案規範）。

## 影響範圍

- **新增**：`src/kinsun/strategies/`（`models.py`／`store.py`／`reflection.py`／`facts.py`）
- **修改**：`db.py`（DDL）、`config.py`（3 個設定）、`composition.py`（掛 `StrategyFacts`）、`scheduler/worker.py`（`run_one` 加第三步）、`reports/reminders.py`（`responded_at`）、`pipeline.py`（標記回應）、`web/routers/admin*.py`（審核端點）
- **不修改**：`agent.py`（核心迴圈零改動）、`safety/`（安全規則完全不受進化影響）
- **文件**：`.env.example`、`AGENTS.md` 命名表（新增 `REFLECTION_` 前綴）、`CONTEXT.md`

## 後續（本次不做）

- 第二階段「某類守則轉自動生效」：以 `category` 的採用率統計為依據，本次已在資料模型預留維度，屆時是開關而非重構。
- 第二層（危急門檻／關鍵詞表自動校正）：需先補 `risk_events.label` 欄位與家屬「真／假警報」標記，見 `docs/archive/dev_docs/危急偵測與誤報處理設計.md:87-88` 的原始設計。
- 第三層（prompt 版本化與 GEPA 最佳化）：接縫在 `agent.py:53`（全系統唯一組裝 system prompt 處）。
