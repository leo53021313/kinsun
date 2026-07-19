# 衛教 RAG 架構設計

本文件定義 KinSun 版本化衛教 RAG 子系統：來源文件 → 清洗／去重 → chunk → Gemini embedding → 候選 release → golden set 品質閘門 → 原子發布 → hybrid retrieval → grounded answer → CareAgent tool。

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
IngestionPipeline（文件、chunks、membership、成功稽核同一 transaction）
  ↓
chunk_text
  ↓
GeminiEmbeddingModel（768 維）
  ↓
PgVectorStore＋PgRagReleaseStore（candidate 不可見；active 原子切換）
  ↓
HealthEducationRetriever（vector + keyword）
  ↓
rerank（trust / source type / freshness / method）
  ↓
AnswerPolicy + optional LLM rewrite
  ↓
health_education_rag tool
  ↓
CareAgent（ToolInvocationContext 帶入上游風險結果）
```

## 資料來源範圍

- `SourceRole.ANSWER`：已核准衛教、醫院與國際來源，可支撐回答。
- `SourceRole.DISCOVERY`：列表首頁、RSS、新聞／open-data API 與 data.gov，只做更新發現與稽核。
- 台灣醫院：臺大、北榮、臺中榮總、長庚、中國醫等衛教文章。
- 國際可信資料：MedlinePlus、WHO 等官方或準官方衛教資料。

安全預設 `RAG_CONTENT_POLICY=allowed_only` 只收 `ALLOWED`。非商用課堂展示可明確改為 `classroom_demo` 保留 `NEEDS_REVIEW`／`DISALLOWED`，metadata 與 Admin 會顯示警告；此決策不得沿用到公開服務。

## 儲存設計

RAG 使用既有 `DATABASE_URL` 的 Supabase Postgres，但和 Mem0 長期記憶完全分表：

- `rag_sources`：來源清冊與 allowlist domain。
- `rag_documents`：單篇文件、hash、metadata。
- `rag_chunks`：chunk 文字、metadata、embedding 模型、`embedding vector(768)`。
- `rag_ingestion_audit_logs`：ingestion 成功／失敗／chunk 數。
- `rag_index_releases`：版本狀態、模型、768 維、內容政策、品質指標與發布時間。
- `rag_release_documents`：release 與文件 membership，未變更內容可安全重用既有 embedding。
- `rag_release_chunks`：release 與 chunk variant membership；相容模型直接重用，不同模型並存，候選版不覆寫 active chunk。
- `rag_calls`：Admin 單輪鏈路使用的檢索觀測與完整 citation。

Embedding 固定 768 維，避免 pgvector 高維索引限制；Mem0 的個人長期記憶仍由 Mem0 自管 collection，不和衛教文件混用。

## Crawler 與 Ingestion

Crawler 行為：

- 只爬 `Source.allowed_domains`。
- 手動建版可 BFS；獨立週更 Worker 只重新抓 active release 已知 URL，不自動收新 discovery。
- 每頁限速與重試，單頁失敗不終止整批。
- Gemini embedding 另有獨立節流與 429／暫時性錯誤退避重試，避免免費額度被瞬間打滿。
- HTML 優先 `main`／`article` 並保留段落；URL 移除 fragment，同 URL 留最新、同 hash 優先 HTTPS 與較短 canonical URL，所有捨棄項寫稽核。
- JSON／RSS／XML 用標準庫解析成 discovery；PDF 用鎖版 `pypdf` 只取文字，掃描 PDF 與圖片記 `skipped`，不做 OCR。
- chunk 依中英文句號、問號、驚嘆號、分號與換行切割；單句過長才硬切並保留 80 字重疊，絕不超過 700 字。

CLI：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.ingest --source hpa_elder_health --max-pages 30
PYTHONPATH=src uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl
PYTHONPATH=src uv run python -m kinsun.rag.ingest --reset --max-pages 20 --delay 2 --embedding-delay 6
```

## Retrieval 與回答

檢索：

- Query normalization 支援台灣用語與台語常見詞，例如「血壓高→高血壓」、「袂睏→睡眠」、「三高→高血壓 高血糖 高血脂」。
- Vector search 使用 pgvector cosine。
- Keyword fallback 使用 title/topic/text 的 `ILIKE`。
- Embedding 或向量搜尋失敗自動改走 keyword；兩路都失敗即回空 evidence，由安全閘門拒答。
- 文件與查詢只讀 `RAG_EMBEDDING_MODEL`。active release 的模型或 768 維與 runtime 不符時，向量路徑停用。
- Rerank 依來源可信度、來源類型、資料新鮮度與檢索方法加權。

回答：

- `HealthEducationRagService.answer()` 先檢索，再套 `AnswerPolicy`。
- 一般衛教可回答；完整 citation 只寫 `rag_calls` 並由 Admin 顯示，不塞進長輩文字／語音。
- 查無證據回 `unsupported`。
- 急症風險以 Agent 前方 `RiskDetector` 為唯一權威，結果透過 `ToolInvocationContext.has_risk_signal` 傳入；RAG 只回 `requires_safety_attention` 稽核旗標，不重跑分級器。
- `CareAgent` 透過 `health_education_rag` tool 使用 RAG，不讓 LLM 憑空回答衛教問題。

## Release 與週更

- 同時最多一個 `building`；candidate 在發布前對線上查詢不可見。
- 閘門：成功率 ≥90%、文件數降幅 ≤20%、零重複 URL／孤兒／空 embedding／超長 chunk，安全案例 100%、top-3 recall ≥80%、unsupported false-positive ≤5%。
- relevance threshold 由 golden set 先守 recall／false-positive，再依 recall 高、false-positive 低、threshold 高決勝。
- 發布在單一 transaction 將舊 active 改 `superseded`、候選改 `active`；失敗不切版。清理保留 active 與前兩個成功版本。
- `PYTHONPATH=src uv run python -m kinsun.rag.worker` 為獨立程序，預設週日 03:00；`scripts/kinsun.sh` 管理其 PID 與 `logs/rag_worker.log`。
