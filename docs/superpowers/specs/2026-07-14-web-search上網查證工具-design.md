# web_search 上網查證工具 設計文件

- 日期：2026-07-14
- 狀態：設計已由 Leo 核可，待實作
- 相關決策：來源分主題控制、只用免費額度（Tavily）、口語帶一句來源＋後台留完整紀錄（資料庫專表）

## 背景與動機

金孫（CareAgent）目前只有三個工具：查天氣（`get_weather`）、報時（`current_time`）、衛教 RAG（`health_education_rag`）。長輩問時事（颱風假、油價）、轉述可疑訊息（謠言、詐騙）、或衛教資料庫沒收錄的健康問題時，金孫完全答不了或只能憑模型舊知識亂答。需要一個「上網查證」工具補上這塊。

涵蓋四種使用情境（Leo 核定，全選）：

1. 長輩問時事、即時資訊
2. 查證謠言、防詐騙
3. 衛教資料庫（RAG）查不到時的備援
4. 一般問題的上網查詢

## 方案選擇

| 方案 | 說明 | 結論 |
| :--- | :--- | :--- |
| A：單一 `web_search` 工具＋topic 參數（Tavily） | 一個工具，依主題帶不同網域白名單 | ✅ 採用 |
| B：Gemini 內建 Google 搜尋（grounding） | 免新金鑰，但無法指定網域白名單，違反分主題控制需求 | ❌ |
| C：拆三個獨立工具 | 描述更精準，但工具數翻倍、prompt 變長、維護量大 | ❌ |

搜尋後端：Tavily Search API。查證事實（2026-07-14）：

- 端點 `POST https://api.tavily.com/search`，Bearer 金鑰驗證（`tvly-` 前綴）。
- 原生支援 `include_domains` 網域白名單（最多 300 個）。
- 免費額度每月 1,000 credits，`search_depth=basic` 每次 1 credit，MVP 階段夠用。

## 元件設計

### 1. 工具：`src/kinsun/tools/web_search.py`

仿 `weather.py` 模式（`ToolSpec` 常數＋`build_web_search_handler` 工廠）。

`WEB_SEARCH_SPEC` 參數：

- `query`（string，必填）：搜尋字串。
- `topic`（string enum，必填）：`general`／`health`／`rumor_check`。

工具描述寫明使用時機：

- 衛教問題**必須先**用 `health_education_rag`；RAG 查不到（unsupported）且非高風險時，才用 `web_search(topic=health)` 備援。
- 長輩轉述可疑訊息、疑似謠言詐騙 → `topic=rumor_check`。
- 時事、油價、生活資訊等一般問題 → `topic=general`。

### 2. 分主題白名單（本檔常數表，集中維護）

| topic | Tavily `include_domains` | 行為 |
| :--- | :--- | :--- |
| `general` | 不限制 | 開放全網搜 |
| `health` | `mohw.gov.tw`（衛福部）、`cdc.gov.tw`（疾管署）、`hpa.gov.tw`（國健署）、`fda.gov.tw`（食藥署）、`nhi.gov.tw`（健保署） | 只搜官方衛教來源 |
| `rumor_check` | `tfc-taiwan.org.tw`（台灣事實查核中心）、`mygopen.com`（MyGoPen）、`165.npa.gov.tw`（165 打詐專網） | 只搜查核網站；查無結果時工具回「查核網站沒有相關紀錄」，金孫保守回覆並建議長輩找家人確認，**不**開放全網重搜 |

未知 `topic` 值：回「（工具參數錯誤，請改用 general、health 或 rumor_check）」讓模型重試，避免健康問題誤搜全網。

### 3. Tavily 呼叫

- 走既有 `kinsun.transport` 傳輸層（`Transport` 可注入、測試用 `FakeTransport`），**不新增依賴套件**。
- 參數：`search_depth=basic`、`max_results=5`、逾時 10 秒（與 weather 一致）。
- 回傳給 LLM 的工具結果為精簡 JSON（仿 `health_rag`）：每筆含 `title`、`site`（網域）、`url`、`content`（摘要），讓金孫能口語帶出來源（「衛福部網站說…」）。

### 4. 來源紀錄：資料庫專表（Leo 核定）

- 資料表 `web_search_lookups`（append-only 流水帳）：

  ```sql
  CREATE TABLE IF NOT EXISTS web_search_lookups (
      web_search_lookup_id TEXT PRIMARY KEY,
      query TEXT NOT NULL,
      topic TEXT NOT NULL,
      status TEXT NOT NULL,          -- ok / empty / error
      sources JSONB NOT NULL,        -- [{title, site, url}]
      created_at DOUBLE PRECISION NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_web_search_lookups_created
      ON web_search_lookups (created_at);
  ```

- DDL 進 `db.py` 的 `ensure_schema`，遵守「建表→遷移→建索引」順序（本表為新表、無遷移段）。
- 持久層三件套（D-42 事件流水帳語意命名）：`src/kinsun/tools/lookups.py`，含 `WebSearchLookupStore`（Protocol）＋`PgWebSearchLookupStore`＋`FakeWebSearchLookupStore`，動詞用 `record`（append-only）。
- **紀錄失敗不影響對話**：`record` 呼叫包 try/except，只留 warning（仿 `safe_record` 精神）。
- 已知限制：工具 handler 拿不到 `elder_id`／`trace_id`（`ToolRegistry.dispatch` 介面只傳 LLM 參數），本表不含長輩關聯；日後需要可用時間戳與 trace 對照，或另案擴充 dispatch 介面。

### 5. 組裝與設定

- 環境變數 `TAVILY_API_KEY`（比照 `GEMINI_API_KEY` 供應商前綴慣例）；`Settings` 新增欄位 `tavily_api_key`（預設空字串）；`.env.example` 同步補上，附中文註解。
- `composition.build_tool_registry` 增加參數（api_key＋lookup store）：金鑰為空字串時**跳過註冊** `web_search`，金孫維持現狀、不會壞（優雅降級）。
- `assemble_core` 建 `PgWebSearchLookupStore(db, clock=clock, new_id=new_id)` 並傳入。

### 6. 系統提示（`agent.py` SYSTEM_PROMPT）增訂

- 衛教問題仍先走 `health_education_rag`，查不到才用 `web_search(topic=health)`。
- 長輩轉述可疑訊息時用 `web_search(topic=rumor_check)` 查證。
- 引用上網查到的內容時，口語帶一句來源（「衛福部網站說…」「查核中心說這是假的」），不唸網址。
- 查無結果時保守回覆，建議長輩與家人確認，不自行補答案。

### 7. 錯誤處理

- Tavily 逾時／連線失敗／額度用完（HTTP 4xx/5xx 均由 `TransportError` 統一承接）：handler 回「（上網查詢暫時失敗，請稍後再試）」；`ToolRegistry.dispatch` 既有兜底保證工具永不拋例外中斷對話。
- 空 `query`：回「請告訴我您想查什麼。」
- 白名單內查無結果（`rumor_check`／`health`）：回明確的「查無」訊息，語意如上表。

### 8. 測試

- `tests/test_tools_web_search.py`（離線，注入 `FakeTransport`）：
  - Bearer header 與端點正確。
  - 依 topic 帶對的 `include_domains`（general 不帶）。
  - 結果格式化為含 title／site／url／content 的 JSON。
  - 空結果、傳輸失敗、空 query、未知 topic 的回覆訊息。
  - 每次查詢有寫入 `FakeWebSearchLookupStore`；store 寫入失敗不影響回傳結果。
- `tests/test_web_search_store_contract.py`：同一份斷言參數化跑 `FakeWebSearchLookupStore`（每次跑）與 `PgWebSearchLookupStore`（`KINSUN_IT=1` 才跑，連 `KINSUN_TEST_DATABASE_URL` 獨立測試庫）。

## 部署前置作業

- Leo 需至 tavily.com 註冊免費金鑰（`tvly-` 開頭），填入 DGX 的 `.env`（`TAVILY_API_KEY`）。
- 純 HTTPS 呼叫，無 ARM64 相容性疑慮；Windows／macOS／DGX 三平台行為一致。

## 文件同步

- `.env.example`：新增 `TAVILY_API_KEY`。
- `CONTEXT.md`（若有工具清單章節）：補 `web_search` 一筆。

## 非目標（YAGNI）

- 不做家屬端來源連結推播（呈現方式已核定為口語帶一句來源）。
- 不做 `rumor_check` 查無後的全網二次搜尋。
- 不做 elder_id／trace_id 關聯（dispatch 介面不動）。
- 不做搜尋結果快取與重試。
