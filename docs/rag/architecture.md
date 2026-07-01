# 衛教 RAG 架構設計

本文件定義 KinSun 完整衛教 RAG 子系統。目標是期末展示可端到端運作的流程：大型 crawler → 清洗 → chunk → Gemini embedding → Supabase Postgres／pgvector → hybrid retrieval → citation → grounded answer → LINE／CareAgent tool。

本系統不是診斷、治療、急救判斷或用藥決策系統；急症、診斷、停藥、調藥仍交給 `RiskDetector`／安全閘門。

## 資料流程

```text
SourceRegistry
  ↓
SourceValidator
  ↓
HealthEducationCrawler
  ↓
DomainParserRegistry / HtmlTextExtractor / optional PDF text extractor
  ↓
IngestionPipeline
  ↓
chunk_text
  ↓
GeminiEmbeddingModel（768 維）
  ↓
PgVectorStore（rag_sources / rag_documents / rag_chunks / audit logs）
  ↓
HealthEducationRetriever（vector + keyword）
  ↓
rerank（trust / source type / freshness / method）
  ↓
AnswerPolicy + optional LLM rewrite
  ↓
health_education_rag tool
  ↓
CareAgent
```

## 資料來源範圍

- 台灣官方／半官方：HPA、MOHW、CDC、FDA、Health99、data.gov.tw 可用衛教資料。
- 台灣醫院：臺大、北榮、臺中榮總、長庚、中國醫等衛教文章。
- 國際可信資料：MedlinePlus、WHO 等官方或準官方衛教資料。

期末專案非商用，授權狀態不作 ingestion 阻擋條件；仍保留 `copyright_status`、`publisher`、`url`、日期與 citation，讓回答可追溯。

## 儲存設計

RAG 使用既有 `DATABASE_URL` 的 Supabase Postgres，但和 Mem0 長期記憶完全分表：

- `rag_sources`：來源清冊與 allowlist domain。
- `rag_documents`：單篇文件、hash、metadata。
- `rag_chunks`：chunk 文字、metadata、`embedding vector(768)`。
- `rag_crawl_jobs`：爬蟲工作紀錄。
- `rag_ingestion_audit_logs`：ingestion 成功／失敗／chunk 數。

Embedding 固定 768 維，避免 pgvector 高維索引限制；Mem0 的個人長期記憶仍由 Mem0 自管 collection，不和衛教文件混用。

## Crawler 與 Ingestion

Crawler 行為：

- 只爬 `Source.allowed_domains`。
- BFS URL discovery，`max_pages_per_source` 控制規模。
- 每頁限速與重試，單頁失敗不終止整批。
- HTML 使用標準庫解析並去除 script/style/nav/footer。
- PDF 文字抽取為可選 `pypdf`；未安裝時該頁記為失敗，不影響 HTML 主線。

CLI：

```bash
uv run python -m kinsun.rag.ingest --source hpa_elder_health --max-pages 30
uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl
uv run python -m kinsun.rag.ingest --reset --max-pages 80
```

## Retrieval 與回答

檢索：

- Query normalization 支援台灣用語與台語常見詞，例如「血壓高→高血壓」、「袂睏→睡眠」、「三高→高血壓 高血糖 高血脂」。
- Vector search 使用 pgvector cosine。
- Keyword fallback 使用 title/topic/text 的 `ILIKE`。
- Rerank 依來源可信度、來源類型、資料新鮮度與檢索方法加權。

回答：

- `HealthEducationRagService.answer()` 先檢索，再套 `AnswerPolicy`。
- 一般衛教可回答，且必須附 citation。
- 查無證據回 `unsupported`。
- 急症、診斷、停藥、調藥、是否急診回 `should_escalate_to_risk_engine=true`。
- `CareAgent` 透過 `health_education_rag` tool 使用 RAG，不讓 LLM 憑空回答衛教問題。
