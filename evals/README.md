# evals — Opik 離線評測

工程視角的離線品質關卡，**不在請求路徑**。分兩類：
（1）**資料集實驗**：對長照／衛教問答資料集跑受測系統，再以 Opik 指標評分；
（2）**對話串級評測**：直接評 Opik 裡已存在的真實對話 thread（多輪），不需資料集。
結果都進 Opik UI 供比對。

## 指標一覽

| 實驗 | 對象 | 指標 | 評什麼 |
| :--- | :--- | :--- | :--- |
| `careline-quality` | dataset `kinsun-careline-smoke` | Hallucination、Moderation | 有沒有編造（防幻覺）、有沒有不當／有害內容 |
| `careline-rag-grounding` | dataset `kinsun-health-rag` | ContextPrecision、ContextRecall、AnswerRelevance | 檢索雜訊多不多、該找的有沒有漏、回答切不切題 |
| `conversation_quality`（thread 級） | Opik 真實 thread（elder_id 串起） | ConversationalCoherence、UserFrustration、SessionCompleteness | 多輪連貫性、長輩挫折感、需求有沒有收尾 |

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

# 跑資料集實驗
PYTHONPATH=src uv run python -m evals.experiments.hallucination     # careline-quality
PYTHONPATH=src uv run python -m evals.experiments.rag_grounding     # careline-rag-grounding（實跑 RAG）

# 跑對話串級評測（不需資料集；評 Opik 裡的真實 thread）
PYTHONPATH=src uv run python -m evals.experiments.conversation_quality
```

跑完到 `http://localhost:5273` 看 experiment 分數與每筆 trace。

對話串級評測（`conversation_quality`）評的是 **Opik 裡已存在的真實 thread**（app 以
`elder_id` 當 `thread_id` 串起、`set_current_trace_io` 寫入每輪內容），故需專案裡先有
夠長的對話 thread（預設只評 `number_of_messages >= 4`；每 thread 取前 20 則以控成本）。

> ⚠️ `evaluate_threads` 會對每條 thread 同時發多個大 prompt（多輪對話 × 各指標），
> Gemini **免費層每分鐘僅 15 次請求**，整批跑很容易被限流擋下（分數 log 不回去）。
> 免費金鑰下建議：改用付費金鑰、或減少指標數／`max_traces_per_thread` 後再跑。

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
