# 衛教 RAG 資料來源與 Chunk Schema

本文件定義資料來源、文件、chunk、citation、answer 與 ingestion audit log 的最小欄位。正式儲存落在 Supabase Postgres／pgvector；JSONL seed 只作 demo 或離線匯入格式。

## Postgres Tables

| table | 用途 |
|---|---|
| `rag_sources` | 來源清冊、publisher、trust、allowlist domain |
| `rag_documents` | 單篇文章／PDF 文字、content hash、topic、日期 |
| `rag_chunks` | chunk 文字、metadata、embedding 模型與 `embedding vector(768)` |
| `rag_ingestion_audit_logs` | ingestion 成功／失敗、chunk 數、parser |
| `rag_index_releases` | 版本、狀態、模型／維度、threshold、品質指標與時間 |
| `rag_release_documents` | release 與文件 membership |
| `rag_release_chunks` | release 與實際 chunk variant membership；隔離不同模型的 embedding |
| `rag_calls` | 查詢觀測、命中、分數、方法與 Admin 完整 citation |

## Chunk Metadata Schema

```json
{
  "source_id": "string",
  "document_id": "string",
  "chunk_id": "string",
  "title": "string",
  "publisher": "string",
  "source_url": "string",
  "source_type": "government | hospital | medical_association | guideline | academic | other",
  "language": "zh-TW | en | mixed",
  "topic": "string",
  "audience": "elder | caregiver | general_public",
  "medical_scope": "health_education | emergency_warning | medication | chronic_disease | prevention | nutrition | exercise | mental_health | other",
  "trust_level": "high | medium | low",
  "approved_for_rag": true,
  "copyright_status": "allowed | needs_review | disallowed",
  "source_published_at": "date|null",
  "source_updated_at": "date|null",
  "retrieved_at": "date",
  "last_reviewed_at": "date|null",
  "version": "string|null",
  "source_role": "answer | discovery"
}
```

`embedding_model` 是 `rag_chunks` 的內部相容性欄位，不放入對外 citation；實際選用的模型以 release 設定與 `rag_release_chunks` membership 為準。

## Source Registry Schema

| 欄位 | 必填 | 說明 |
|---|---|---|
| `source_id` | 是 | 穩定 ID，不隨 URL 變更 |
| `title` | 是 | 來源標題 |
| `url` | 是 | 入口或文件 URL |
| `publisher` | 是 | 發布單位 |
| `source_type` | 是 | government／hospital／international_official 等 |
| `trust_level` | 是 | high／medium／low |
| `copyright_status` | 是 | allowed／needs_review／disallowed |
| `recommended_status` | 是 | approved／conditional／rejected／out_of_scope |
| `approved_for_rag` | 是 | 是否允許 ingestion；期末非商用展示不以授權狀態阻擋 |
| `allowed_domains` | 是 | crawler allowlist |
| `notes` | 否 | 驗證理由 |
| `role` | 是 | `answer` 可支撐回答；`discovery` 只找更新與留稽核 |

## JSONL Seed Schema

`PYTHONPATH=src uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl`

```json
{
  "source_id": "hpa_elder_health",
  "url": "https://example",
  "title": "高血壓衛教",
  "publisher": "衛生福利部國民健康署",
  "text": "文件純文字",
  "topic": "高血壓",
  "language": "zh-TW",
  "audience": "general_public",
  "medical_scope": "health_education",
  "published_at": "2026-01-01",
  "updated_at": "2026-01-01"
}
```

## Citation Schema

```json
{
  "source_id": "string",
  "title": "string",
  "publisher": "string",
  "url": "string",
  "chunk_id": "string"
}
```

## Answer Schema

```json
{
  "answer": "string",
  "safety_level": "normal | caution | urgent | unsupported",
  "requires_safety_attention": false,
  "reason": "string"
}
```

完整 `citations` 與 evidence 分數不進長輩工具 payload，只存 `rag_calls` 供 Admin 稽核。

## Ingestion Audit Log

| 欄位 | 說明 |
|---|---|
| `source_id` | 來源 ID |
| `fetched_at` | 抓取時間 |
| `content_hash` | 原始內容雜湊 |
| `chunk_count` | 產生 chunk 數 |
| `parser_used` | 使用的 parser |
| `status` | success／skipped／failed |
| `error_message` | 錯誤訊息，成功時為 null |
| `operator_or_job_id` | 人工操作者或排程 job id |

## 權限與隱私

- metadata 不得包含長輩姓名、電話、地址、LINE ID 或逐字稿。
- ingestion audit log 不記錄查詢者或長輩對話。
- 未來若加入家屬或長照機構權限，應在文件層與查詢層分開控管。
