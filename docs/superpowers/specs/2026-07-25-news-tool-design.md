# get_news 工具設計（2026-07-25）

> 狀態：✅ Leo 核可方向（2026-07-25，選項「加一個 get_news 工具」）；細節依既有工具慣例由施工者定，載明於本文件。

## 目標

讓模型在聊天中可以主動查最近新聞——長輩問「最近有什麼新聞」時，金孫用的是自家爬好的 `news_items` 表（衛福部＋News API），而不是只能靠 web_search。

## 背景與範圍

- D-74（PR #75）話題新聞模組現況：排程爬蟲每晚寫 `news_items` 表，早上問候把標題織進 intent；模型**沒有**工具可主動查。
- 本工項＝**消費端補一個 LLM 工具**，比照 transport 模式（生產／消費分離）：爬蟲、資料表、排程 job 全部留在 `news/` 原地不動。

## 設計

### 新增 `src/kinsun/tools/news.py`（模板＝`clock.py`）

- `NEWS_SPEC = ToolSpec(name="get_news", parameters 無參數)`——描述寫明「長輩問最近有什麼新聞、想聊時事時使用」。
- `build_news_handler(store: NewsStore, *, clock, window_days=3, limit=5)`：
  - 讀 `store.list_recent(since=now - window_days*86400)`，取前 `limit` 則。
  - 回口語字串：逐則「（發布媒體）標題」；查無資料回「目前沒有最新的新聞資料」口語提示。
  - `NewsError` 在 handler 內接住、回口語提示（比照 transport「TransportError 一律回口語提示、不拋」；registry.dispatch 的兜底仍在）。
- 視窗取 3 天非 1 天：爬蟲一晚失敗時聊天工具仍有料可講（問候端維持 1 天不動）。

### 接線（`composition.py`）

- `build_tool_registry` 加參數 `news: NewsStore | None = None`；有給才註冊（None＝測試情境不註冊）。
- `assemble_core` 把 `PgNewsStore(db)` 提前建立，同時餵給 registry 與 Core（原本只在 Core 尾端 inline 建）。

### 不做（YAGNI）

- 不加環境變數（window/limit 寫死，比照工具迴圈上限）；不做主題過濾參數；不動 news/ 任何檔案。

## 測試（TDD）

`tests/test_tools_news.py`：回傳含標題與媒體名／上限 5 則／視窗外排除／空資料口語提示／store 故障口語降級。
`tests/test_composition.py`：有 news store→get_news 有註冊；baseline（未給 store）維持原 4 工具不變。

## 文件同步（15 §2）

07 §1 tools 列補 news 工具、08 tools/ 樹補 news.py、05 若有工具清單一併補、README 狀態表。
