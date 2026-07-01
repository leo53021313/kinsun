# 金孫 KinSun

> 聽懂國台語的長輩 AI 語音陪伴守護 Agent。

AIPE03 第五組期末專案。

## 專案文件

| 文件 | 內容 |
|------|------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | 多人協作流程（分支、PR、合併規則）— **開始開發前必讀** |
| [AGENTS.md](AGENTS.md) | 開發規範（程式碼品質、安全性、測試…），所有 AI 代理共用 |
| [progress.md](progress.md) | 開發進度快照（已完成模組、架構、程式結構、待辦） |
| [docs/](docs/) | 策略/設計文件、各模組 spec 與實作計畫 |

## 開發團隊

7 人協作，採「每人一分支 + 整合負責人」模型，整合負責人為 Leo（@leo53021313）。
詳見 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 快速開始

> 程式結構見 [progress.md](progress.md)（§4）；以下為開發環境設定。

本專案使用 [uv](https://docs.astral.sh/uv/) 管理依賴與虛擬環境，Python 統一 3.12。

### 1. 安裝 uv（只需一次）

```powershell
# Windows（PowerShell）
irm https://astral.sh/uv/install.ps1 | iex
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 取得專案並切到自己的分支

```bash
git clone https://github.com/leo53021313/kinsun.git
cd kinsun
git checkout <你的分支>   # 例如 git checkout Leo
```

### 3. 建立環境（自動裝 Python 3.12 + 所有依賴）

```bash
uv sync
uv run pre-commit install   # 啟用 commit 前自動檢查（ruff lint/format）
```

完成後即可開發。常用指令：

| 指令 | 作用 |
|------|------|
| `uv add <套件>` | 新增執行依賴 |
| `uv add --dev <套件>` | 新增開發依賴 |
| `uv run <指令>` | 在專案環境內執行（如 `uv run python main.py`） |
| `uv run ruff check .` | 手動跑 lint |
| `uv run ruff format .` | 手動排版 |

接著請閱讀 [CONTRIBUTING.md](CONTRIBUTING.md) 了解協作流程。

## 啟動本機開發

> ⚠️ 記憶層已上雲：啟動 webhook／scheduler **一定要**雲端金鑰，否則會在建表（`ensure_schema`）就失敗。
> 單元測試不受影響（全離線、注入 fake，不需金鑰）。各模組設計見 [docs/superpowers/specs/](docs/superpowers/specs/)、實作計畫見 [docs/superpowers/plans/](docs/superpowers/plans/)。

1. 複製 `.env.example` 為 `.env`，至少填入：
   - **LINE**：`LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`
   - **Gemini**：`GEMINI_API_KEY`
   - **Supabase Postgres**：`DATABASE_URL`（短期記憶＋帳號＋Mem0 長期記憶向量共用）
   - ASR 先用 `mock`（不需 GPU）。

2. 啟動 webhook（對話主流程）：

   ```bash
   uv run uvicorn --app-dir src "kinsun.app:build_app" --factory --reload --port 8000
   ```

3. 啟動排程 worker（每日記憶整理、定時問候、失聯關心；另開一個終端）：

   ```bash
   # macOS / Linux
   PYTHONPATH=src uv run python -m kinsun.scheduler
   ```

   ```powershell
   # Windows（PowerShell）
   $env:PYTHONPATH="src"; uv run python -m kinsun.scheduler
   ```

4. 用 ngrok 之類工具把 `https://<你的網域>/line/webhook` 設為 LINE 的 Webhook URL，對 LINE 官方帳號傳語音即可收到金孫回覆（dev 期 ASR 為 mock 文字）。

> 真實 ASR：在 DGX 啟動 [`services/asr`](services/asr/)，並把 `.env` 改為 `ASR_BACKEND=dgx`、`ASR_ENDPOINT=http://<dgx>:8001/transcribe`。
> 台語 TTS 服務骨架見 [`services/tts`](services/tts/)（待接 DGX）。

執行測試（全離線、不需 GPU/金鑰；雲端整合測試需 `KINSUN_IT=1` + 真金鑰才會跑）：

```bash
uv run pytest
```

## 衛教 RAG ingestion

衛教 RAG 使用同一組 `DATABASE_URL`，但以 `rag_sources`、`rag_documents`、`rag_chunks` 等獨立資料表和 Mem0 長期記憶分開。Supabase 需啟用 pgvector。

匯入期末展示 seed：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl
```

```powershell
$env:PYTHONPATH="src"; uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl
```

啟動大型 crawler：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.ingest --max-pages 80
```

```powershell
$env:PYTHONPATH="src"; uv run python -m kinsun.rag.ingest --max-pages 80
```

指定單一來源重建：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.ingest --reset --source hpa_elder_health --max-pages 30
```

```powershell
$env:PYTHONPATH="src"; uv run python -m kinsun.rag.ingest --reset --source hpa_elder_health --max-pages 30
```
