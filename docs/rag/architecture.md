# 衛教 RAG 架構設計

本文件定義 KinSun 衛教 RAG 子系統的邊界、資料流程、檢索流程與整合位置。它不是診斷系統，也不取代既有 `RiskDetector`。

## 為什麼需要這項修改

目前 Care Agent 會直接把長輩文字交給 LLM 產生回覆。雖然系統提示已要求不要診斷或給藥，但只靠 prompt 無法保證健康資訊正確、可追溯或可稽核。衛教 RAG 的目標是把「可回答的健康知識」限制在可信來源與引用範圍內。

## 方案比較

| 方案 | 優點 | 缺點 | 結論 |
|---|---|---|---|
| LangChain／LlamaIndex／Haystack | 功能完整，connector 多 | 依賴重、抽象多、初期審計成本高 | 暫不採用 |
| Qdrant／pgvector／Meilisearch | 可擴充到 production 檢索 | 需要服務、部署、維運與 schema 決策 | 文件預留，第一階段不導入 |
| OpenAI Vector Stores | 快速託管向量索引 | 供應商綁定與資料治理需評估 | 暫不採用 |
| 自研 minimal pipeline + in-memory mock | 可測、可審計、無新增依賴 | 不適合大量資料或 production 效能 | 第一階段採用 |

第一階段採用 minimal interface：先定義 schema、政策、retriever 與 answer gate，讓安全邏輯可測；未來可替換 vector store 與 keyword index。

## RAG 邊界

RAG 可以做：

- 一般衛教知識查詢。
- 長輩常見健康主題說明。
- 飲食、睡眠、運動、慢性病自我照護的一般衛教。
- 根據可信來源生成簡短、口語化、長輩可理解的回答。
- 回答時附上來源 citation。

RAG 不可以做：

- 診斷疾病。
- 開藥、停藥、調藥。
- 判斷是否需要急診。
- 取代醫師、護理師、藥師、照護員。
- 對高風險症狀自行下結論。
- 在沒有來源支持時給醫療建議。

## 與 KinSun 既有架構的整合位置

```text
Care Agent / Response Planner
        ↓
Health Education RAG
        ↓
LLM Rewriter
        ↓
Safety Guard
        ↓
Response to elder / caregiver
```

Risk Engine 必須獨立：

```text
Transcript / NLU entities
        ↓
Risk Engine
        ↓
Risk Level / Escalation Policy
```

設計原則：

- `RiskDetector` 先處理紅旗症狀、急症、自傷、跌倒重傷、診斷請求與用藥請求。
- RAG 只能在 Response Planner 需要衛教補充時被呼叫。
- RAG 回傳 `should_escalate_to_risk_engine=true` 時，代表「不要使用 RAG 回答健康內容」，不是最終通知決策。
- 最終通知家屬、119、1922 或其他通道仍由 Risk Engine／Escalation Policy 決定。

## Ingestion Pipeline

```text
Source registry
  ↓
Source validator
  ↓
Document fetcher / loader
  ↓
Text extractor
  ↓
Cleaner / boilerplate remover
  ↓
Chunker
  ↓
Metadata enricher
  ↓
Embedding generator
  ↓
Vector index writer
  ↓
Keyword index writer
  ↓
Ingestion audit log
  ↓
Re-index / refresh mechanism
```

每次 ingestion 必須留下 audit log：

```text
source_id
fetched_at
content_hash
chunk_count
parser_used
status
error_message
operator / job_id
```

第一階段只實作 interface 與 in-memory mock；正式 fetcher 必須遵守：

- 僅抓 allowlist 網域。
- 遵守 robots.txt、crawl-delay 與 API 限制。
- 僅抓 `approved` 來源；`conditional` 需人工核准後才可開啟。
- 不記錄長輩個資或逐字稿到 ingestion log。

## Retrieval Pipeline

```text
User query
  ↓
Query normalization
  ↓
台灣繁中／台語混合用語處理
  ↓
Metadata filtering
  ↓
Hybrid retrieval：vector search + keyword / BM25
  ↓
Reranking
  ↓
Source trust weighting
  ↓
Recency weighting
  ↓
Duplicate chunk removal
  ↓
Citation assembly
  ↓
Evidence threshold
  ↓
Answer gating
```

第一階段 query normalization 先處理少量高價值同義詞，例如：

- `血壓高` → `高血壓`
- `睡不著`、`袂睏`、`睏袂去` → `睡眠`
- `阿公`、`阿嬤`、`老人` → `長者`
- `胸口悶`、`喘不過氣`、`喘袂過氣` → 不直接回答，交給 Risk Engine

## Evidence Threshold 與 Answer Gating

RAG 只有在同時符合以下條件時才可回答：

- 至少有一個 `approved_for_rag=true` 的 chunk。
- chunk 來源 `trust_level` 為 `high` 或經人工核准的 `medium`。
- `copyright_status=allowed`。
- citation 可完整組出 `source_id`、`title`、`publisher`、`url`、`chunk_id`。
- 查詢不是診斷、用藥調整、急症或自傷風險情境。

若證據不足，回答必須採固定拒答：

```text
目前查不到足夠可信的衛教資料，我不能亂給健康建議。
請詢問醫師、護理師或藥師；若是緊急不舒服，請立即聯絡家人或撥 119。
```

## 資料儲存與索引

第一階段：

- `SourceRegistry`：Python dataclass 清單。
- `InMemoryKeywordIndex`：測試用關鍵字索引。
- `InMemoryVectorStore`：測試用向量儲存介面。
- 不新增資料庫、不新增第三方套件。

未來 production 可替換為：

- PostgreSQL + pgvector：適合資料治理與 metadata filtering。
- Qdrant：適合高效向量檢索。
- Meilisearch／OpenSearch：適合 BM25 與中文 keyword retrieval。

替換時不可改變 answer policy 與 citation schema。
