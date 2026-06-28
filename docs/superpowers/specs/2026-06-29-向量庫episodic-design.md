# 向量庫（episodic 情緒記憶）v1 設計

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：⑦ 記憶／資料層的「向量庫（閒聊／情緒片段，episodic）」。
> 長期記憶子系統第二塊；第一塊見 [2026-06-29-知識圖譜v1-design](2026-06-29-知識圖譜v1-design.md)。

---

## 1. 背景與目標

長期記憶在架構上分三塊：骨幹（路由）／知識圖譜（結構化事實，已完成）／**向量庫（閒聊／情緒片段，episodic）**。本 spec 做第二塊。

**完成後：** 每日把對話中**有情緒意義的片段**抽出、向量化存庫；回覆前用長者當下這句話做**語意檢索**，撈最相關的幾段餵 agent，讓金孫「記得你上次聊過很想孫子」。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* 每日批次（可觸發函式 + CLI）：今日對話 → LLM 抽情緒片段 → Gemini embeddings → 存 SQLite。
* 語意檢索：embed 查詢 → Python 餘弦取 top-k → 注入 agent。
* 新增「記憶情境聚合器」`MemoryContext`：把知識事實（不看查詢）＋情緒片段（依查詢）組成一段，供 agent 注入。
* 短期／知識／情緒**三個分開的 DB**。

### 2.2 不在範圍內（後續）
* 長期記憶骨幹（把每日抽取統一路由到知識圖譜／向量庫；本 spec 的 episodic 批次先獨立）。
* Cron 排程（切片②）。
* 線上 DB：`VectorStore` 介面不變，未來換 `PgVectorStore`（Postgres + pgvector）。
* 進階檢索（重排序、時間衰減、多查詢）。

---

## 3. 元件與檔案

```
src/kinsun/episodic/
  __init__.py
  embeddings.py   # Embedder(Protocol) + EmbeddingError + GeminiEmbedder
  store.py        # VectorStore(Protocol) + SqliteVectorStore + _cosine
  extractor.py    # EpisodeExtractor + _parse_episodes（純函式）
  recall.py       # EpisodicRecaller
  batch.py        # run_episode_extraction + main（CLI）
src/kinsun/
  recall.py       # MemoryContext（聚合知識＋情緒）
  agent.py        # 改：依賴 MemoryContext，handle 用 recall(session_id, user_text)
  app.py / config.py  # 改：組裝與設定
```

### 3.1 Embeddings（embeddings.py）
```python
class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...

class GeminiEmbedder:  # 走既有 google-genai；網路呼叫不單測
    def __init__(self, *, api_key: str, model: str) -> None: ...
    def embed(self, text: str) -> list[float]: ...  # 失敗拋 EmbeddingError
```
`EmbeddingError(Exception)`。Gemini embeddings 模型 id 於實作時查證並設為 `EMBEDDING_MODEL` 預設。

### 3.2 向量儲存（store.py）
```python
class VectorStore(Protocol):
    def add(self, session_id: str, content: str, embedding: list[float]) -> None: ...
    def search(self, session_id: str, embedding: list[float], k: int) -> list[str]: ...

def _cosine(a: list[float], b: list[float]) -> float: ...  # 純 Python；任一零向量回 0.0
```
`SqliteVectorStore(db_path)`：
* 表 `episodes(id, session_id, content, embedding TEXT)`，`embedding` 存 JSON；唯一索引 `(session_id, content)` 去重。
* `add`：`INSERT OR IGNORE`。
* `search`：載入該 session 全部 → 算 `_cosine(query, each)` → 由高到低取前 k → 回 `list[str]`（content）；無資料回 `[]`。
* 維度無關（JSON 存任意長度），SQLite 不需固定維度。
* DB 例外包成 `VectorStoreError`。

### 3.3 抽取（extractor.py）
* `EpisodeExtractor(llm)`：要求 LLM 從今日對話抽**有情緒意義的閒聊片段**，輸出 **JSON 字串陣列**（每段一句簡述）。
* `_parse_episodes(raw) -> list[str]`：純函式；解析、僅留非空字串；**壞 JSON → 空 list**（fail-safe）。
* LLM 失敗 → 空 list。

### 3.4 檢索（recall.py，episodic）
```python
class EpisodicRecaller:
    def __init__(self, embedder: Embedder, store: VectorStore, *, top_k: int = 3) -> None: ...
    def recall(self, session_id: str, query: str) -> str: ...
```
* embed 查詢 → `store.search` top-k → 格式化前綴「你記得這位長者先前聊過：…」。
* 無結果 → `""`；embed／搜尋失敗 → `""`（**fail-safe**，不拋例外）。

### 3.5 批次（batch.py，episodic）
* `run_episode_extraction(session_id, *, short_term, extractor, embedder, store) -> int`：今日短期 → 抽片段 → 逐段 embed（**失敗就跳過該段**）→ `add` → 回成功存入數。
* `main(argv)`：CLI（`python -m kinsun.episodic.batch <session_id>`）。

---

## 4. 記憶情境聚合器與 agent 整合

### 4.1 `src/kinsun/recall.py` — `MemoryContext`
```python
class MemoryContext:
    def __init__(self, knowledge, episodic) -> None: ...
    def recall(self, session_id: str, user_text: str) -> str:
        # = knowledge.recall(session_id) + episodic.recall(session_id, user_text)
```
`knowledge` 為 `KnowledgeRecaller`（`recall(session_id)`）、`episodic` 為 `EpisodicRecaller`（`recall(session_id, query)`）。

### 4.2 CareAgent 改動
* `CareAgent(llm, memory, context)`：把原本的 `recaller` 換成 `context`（`recall(session_id, user_text) -> str`）。
* `handle`：`system_prompt = SYSTEM_PROMPT + context.recall(session_id, user_text)`。
* `app.py`：`context = MemoryContext(KnowledgeRecaller(SqliteFactStore(...)), EpisodicRecaller(GeminiEmbedder(...), SqliteVectorStore(...)))`。
* `pipeline`/`webhook` 測試的 agent 建構，`recall` 測試替身改為 `recall(session_id, user_text)`。

---

## 5. 設定新增（環境變數）

| 變數 | 用途 | 預設 |
|------|------|------|
| `EPISODIC_DB_PATH` | 向量庫 SQLite 路徑 | `kinsun_episodic.db` |
| `EPISODIC_TOP_K` | 檢索取回片段數 | `3` |
| `EMBEDDING_MODEL` | Gemini embeddings 模型 id | （實作時查證後填預設） |

---

## 6. 錯誤處理（可靠性）

* embed／抽取／檢索／DB **全 fail-safe**：壞掉退化成「沒有情緒記憶」，**絕不中斷對話**。
* `EpisodicRecaller.recall` 任何例外 → `""`。
* 批次中單段 embed 失敗 → 跳過該段、續抽其餘。
* 自訂 `EmbeddingError`、`VectorStoreError` 供辨識。

---

## 7. 測試策略（全本機，不需網路）

* `test_episodic_store`：用固定向量驗 `_cosine`；`add`＋`search` 依餘弦排序取 top-k；去重；session 隔離；空回 `[]`。
* `test_episodic_extractor`：`_parse_episodes` 解析字串陣列、壞 JSON→`[]`、跳空字串；fake LLM 整合、LLM 失敗→`[]`。
* `test_episodic_recall`：fake embedder+store → 格式化字串；無結果→`""`；embed 拋錯→`""`。
* `test_memory_context`：知識＋情緒字串組合；任一空仍正確。
* `test_episodic_batch`：fakes 串接、回成功數；某段 embed 失敗→跳過。
* `test_agent`：`context.recall(session_id, user_text)` 注入 system prompt（測試替身更新）。

---

## 8. 已定預設值（列出供否決）

* 情緒片段由 **LLM 抽取**（非直接 embed 原始對話）。
* 去重鍵 `(session_id, content)`。
* `top_k=3`；三個 DB 分檔。
* 餘弦用純 Python（N 小）；`VectorStore` 介面留給 pgvector。
* 無新依賴（Gemini embeddings 走既有 google-genai；`math`/`json` 為 stdlib）。
