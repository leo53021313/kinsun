# evals — Opik 離線評測

工程視角的離線品質關卡，**不在請求路徑**。用來對長照問答資料集跑 Gemini，
再以 Opik 的 LLM-as-judge 指標（如 Hallucination＝防幻覺）評分，結果進 Opik UI。

## 前置

- 自架 Opik 在跑（DGX：`cd /home/leo29/opik && ./opik.sh`，UI `http://localhost:5273`）。
- `OPIK_ENABLED=true`、`GEMINI_API_KEY` 已設。

## 執行

從 repo 根目錄執行（`PYTHONPATH=src` 讓 `kinsun` 可匯入，比照 pytest 的設定）：

```bash
export OPIK_ENABLED=true
PYTHONPATH=src uv run python -m evals.datasets.careline_smoke     # 上傳資料集（一次）
PYTHONPATH=src uv run python -m evals.experiments.hallucination   # 跑實驗
```

跑完到 `http://localhost:5273` 看 experiment 分數與每筆 trace。

## 結構

- `datasets/`：資料集定義（上傳成 Opik dataset）。
- `experiments/`：實驗腳本（對 dataset 跑受測系統 + 指標）。

新增指標（如 ContextPrecision/ContextRecall）時，在 `experiments/` 加對應腳本，
資料集需附檢索情境（`context` 欄位）。
