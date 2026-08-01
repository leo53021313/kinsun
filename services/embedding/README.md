# 地端嵌入服務（BGE-M3）

衛教 RAG 的向量化後端。僅在 DGX Spark（Linux + ARM64 + GPU）執行；
應用層透過 `RAG_EMBEDDING_ENDPOINT` 呼叫，與模型是否同機無關。

## 為什麼換掉 Gemini

2026-08-01 A/B 實測，語料為國健署 1,113 篇真文章、2,267 個 chunk：

| 模型 | 一般口語 61 題 R@1／MRR | 台語詞彙 21 題 R@1／MRR | 全站 5,667 篇建置 |
| :--- | :--- | :--- | :--- |
| Gemini gemini-embedding-001（768 維） | 78.7%／0.885 | **95.2%／0.968** | 約 2.9 小時 |
| **BGE-M3（1024 維）** | **82.0%／0.900** | 85.7%／0.896 | **約 2 分鐘** |
| Qwen3-Embedding-0.6B（1024 維） | 80.3%／0.884 | 81.0%／0.859 | 約 6 分鐘 |

- 一般口語 BGE-M3 兩項指標都勝過 Gemini；台語詞彙 Gemini 較強，差距為 21 題中的 2 題。
- 台語弱勢由 `retriever._SYNONYMS` 的同義詞展開補回（實測 R@3 90.5% → 95.2%）。
- 決定性因素是建置成本：Gemini 免費層每支金鑰每日約 1,000 次，一輪建置燒掉三支金鑰、
  跑近三小時；地端沒有配額，重建隨時可做。

## 安裝與啟動

```bash
# DGX 上（沿用與 services/asr 相同的套件版本）
python -m venv services/embedding/.venv
services/embedding/.venv/bin/pip install -r services/embedding/requirements.txt

# 首次啟動會自動下載模型（約 1.3 GB，快取在 ~/.cache/huggingface）
services/embedding/.venv/bin/python -m uvicorn services.embedding.server:app \
  --host 0.0.0.0 --port 8003
```

## 環境變數

本服務的變數獨立管理，不經 `config.py`（與 `services/asr`、`services/tts` 一致）。

| 變數 | 預設 | 說明 |
| :--- | :--- | :--- |
| `EMBEDDING_MODEL_ID` | `BAAI/bge-m3` | HuggingFace 模型代號 |
| `EMBEDDING_DIMENSIONS` | `1024` | 向量維度，須與 `rag_chunks.embedding` 一致 |
| `EMBEDDING_MAX_CONCURRENCY` | `1` | 同時進模型的請求數 |
| `EMBEDDING_MAX_QUEUE` | `8` | 排隊上限，超過回 503 |
| `EMBEDDING_MAX_BATCH` | `64` | 單次請求最多幾段文字，超過回 413 |
| `EMBEDDING_MAX_TOKENS` | `1024` | 單段截斷長度（BGE-M3 支援到 8192） |
| `EMBEDDING_API_KEY` | 空 | 設定後驗 `X-Api-Key`；未設＝內網開發模式 |
| `EMBEDDING_PRELOAD` | `0` | 設 `1` 在啟動時先載入模型 |

## API

```bash
curl -s -X POST http://127.0.0.1:8003/embed \
  -H 'Content-Type: application/json' \
  -d '{"texts": ["高血壓的長者要注意什麼？"]}' | head -c 200
# {"vectors":[[0.0123,...]],"model":"BAAI/bge-m3","dimensions":1024}

curl -s http://127.0.0.1:8003/healthz
# {"status":"ok","model":"BAAI/bge-m3","dimensions":1024,"model_loaded":true}
```

## 兩個容易踩的坑

**padding 方向必須配合 pooling。** BGE-M3 的 dense 向量取 CLS（位置 0），
tokenizer 必須 `padding_side="right"`。2026-08-01 實測誤設成 `left` 時 R@1 從
98.4% 掉到 39.3%——數字看起來只像「這個模型比較差」，非常難察覺。

**文件要帶標題。** 呼叫端把標題併進文字再送出（`LocalEmbeddingModel.embed_document`
已內建）。實測含標題 R@1 98.4%、純內文 85.2%。

## 相關文件

- 呼叫端：`src/kinsun/rag/embeddings.py` 的 `LocalEmbeddingModel`
- 部署與維運：`docs/dev/14_部署與運維.md`
