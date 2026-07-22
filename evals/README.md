# evals — Opik 離線評測

工程視角的離線品質關卡，**不在請求路徑**。對長照／衛教問答資料集跑受測系統，
再以 Opik 的指標（LLM-as-judge）評分，結果進 Opik UI 供比對。

## 指標一覽

| 實驗 | 資料集 | 指標 | 評什麼 |
| :--- | :--- | :--- | :--- |
| `careline-quality` | `kinsun-careline-smoke` | Hallucination、Moderation | 有沒有編造（防幻覺）、有沒有不當／有害內容 |
| `careline-rag-grounding` | `kinsun-health-rag` | ContextPrecision、ContextRecall、AnswerRelevance | 檢索雜訊多不多、該找的有沒有漏、回答切不切題 |

## 前置

- 自架 Opik 在跑（DGX：`cd /home/leo29/opik && ./opik.sh`，UI `http://localhost:5273`）。
- `OPIK_ENABLED=true`、`GEMINI_API_KEY` 已設。
- **RAG 實驗額外需**：`DATABASE_URL` 指向「含 active release 衛教向量庫」的資料庫
  （`rag_grounding` 會實跑真實 retriever；無資料時檢索回空，分數會偏低但仍可跑）。

## 執行

從 repo 根目錄執行（`PYTHONPATH=src` 讓 `kinsun` 可匯入，比照 pytest 的設定）：

```bash
export OPIK_ENABLED=true

# 上傳資料集（各一次即可）
PYTHONPATH=src uv run python -m evals.datasets.careline_smoke
PYTHONPATH=src uv run python -m evals.datasets.health_rag

# 跑實驗
PYTHONPATH=src uv run python -m evals.experiments.hallucination     # careline-quality
PYTHONPATH=src uv run python -m evals.experiments.rag_grounding     # careline-rag-grounding（實跑 RAG）
```

跑完到 `http://localhost:5273` 看 experiment 分數與每筆 trace。

> 提醒：RAG 實驗每筆都會呼叫 Gemini（檢索 embedding ＋ 答案改寫），LLM-judge 指標
> 也逐筆呼叫模型，會產生 API 成本並讀取衛教向量庫，請在確認資料集大小後再整批跑。
>
> LLM-judge 指標預設走 OpenAI；本專案改用 Gemini 當裁判（`model="gemini/<模型>"`，讀
> `GEMINI_API_KEY`）。實驗已設 `task_threads=1` 序列化以緩解 Gemini **免費層 RPM 限流**；
> 若仍見 429（`retryDelay`）代表當分鐘配額用盡，稍等或改用付費金鑰再整批跑。

## 結構

- `datasets/`：資料集定義（上傳成 Opik dataset）。
- `experiments/`：實驗腳本（對 dataset 跑受測系統 + 指標）。

新增 RAG 指標時，資料集需附 `input`／`expected_output`，context 由實驗實跑
retriever 取得（見 `experiments/rag_grounding.py`），不寫死在資料集。
