# 金孫 KinSun

> 聽懂國台語的長輩 AI 語音陪伴守護 Agent。

AIPE03 第五組期末專案。

## 專案文件

| 文件 | 內容 |
|------|------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | 多人協作流程（分支、PR、合併規則）— **開始開發前必讀** |
| [AGENTS.md](AGENTS.md) | 開發規範（程式碼品質、安全性、測試…），所有 AI 代理共用 |
| [progress.md](progress.md) | 開發進度快照（已完成模組、架構、程式結構、待辦） |
| [docs/mvp/](docs/mvp/) | MVP 階段文件組合（PRD、User Flow、API/DB Spec、測試清單…），含待議決策標記 |
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
   PYTHONPATH=src uv run python -m kinsun.cron
   ```

   ```powershell
   # Windows（PowerShell）
   $env:PYTHONPATH="src"; uv run python -m kinsun.cron
   ```

4. 用 ngrok 之類工具把 `https://<你的網域>/line/webhook` 設為 LINE 的 Webhook URL，對 LINE 官方帳號傳語音即可收到金孫回覆（dev 期 ASR 為 mock 文字）。

> 真實 ASR：在 DGX 啟動 [`services/asr`](services/asr/)，並把 `.env` 改為 `ASR_BACKEND=dgx`、`ASR_ENDPOINT=http://<dgx>:8001/transcribe`。
>
> 真實 TTS：在 DGX 啟動 [`services/tts`](services/tts/)（CosyVoice 3，程式碼已實作，**尚待 DGX 實機驗證**），
> 應用層 `.env` 改為 `TTS_BACKEND=dgx`、`TTS_ENDPOINT=http://<dgx>:8002/synthesize`；另可選填
> `TTS_TIMEOUT_SECONDS`（合成逾時秒數，預設 `30`）、`TTS_REPLY_TEXT`（`true`＝語音＋文字、`false`＝只回語音，預設 `true`）。
> 語音回覆會把音檔上傳 Supabase Storage 取得公開 URL 供 LINE 播放，需另設
> `SUPABASE_URL`、`SUPABASE_SERVICE_KEY`（Supabase 專案 URL 與 service key）、
> `AUDIO_BUCKET`（bucket 名稱，預設 `tts-audio`）、`AUDIO_RETENTION_DAYS`（音檔保留天數，預設 `2`，逾期由每日排程清理）、
> `AUDIO_UPLOAD_TIMEOUT_SECONDS`（上傳逾時秒數，預設 `10`）。
>
> ⚠️ **一次性設定**：需先在 [Supabase 後台](https://supabase.com/dashboard) 手動建立一個名為 `tts-audio`
> （或對應 `AUDIO_BUCKET` 設定值）的**公開（Public）Storage bucket**，音檔才能以公開 URL 供 LINE 播放。

執行測試：

```bash
scripts/test_db.sh up   # 起本機測試庫（Docker／pgvector，只需第一次；重開機會自動回來）
uv run pytest           # 單元測試全離線；Pg 整合測試自動連上面那個測試庫
```

`.env` 的 `KINSUN_IT=1` 與 `KINSUN_TEST_DATABASE_URL` 讓整合測試預設就跑（設定見 `.env.example`）。
測試庫沒起著時，Pg 測試會**直接紅並提示**——刻意不 skip：整合測試靜默跳過，正是 `ensure_schema`
遷移缺陷溜到正式庫才爆的原因。要暫時關掉整批 Pg 測試，把 `.env` 的 `KINSUN_IT` 改成 `0`。
測試庫是拋棄式的，與正式庫無關；`scripts/test_db.sh down`／`reset` 可隨時丟棄重來。

> 雲端整合測試（Gemini／Mem0 等真金鑰）另需對應金鑰才會跑，否則自動 skip。

## 衛教 RAG ingestion

衛教 RAG 使用同一組 `DATABASE_URL`，但以獨立資料表和 Mem0 長期記憶分開。線上查詢只讀 `active` release；所有匯入先建立候選版，通過品質閘門才原子發布，失敗時舊版不受影響。Supabase 需啟用 pgvector。

同一個個人 Supabase 原地升級時只需既有 `DATABASE_URL`。`--in-place` 先以同一個唯讀交易載入原始備份紀錄與正規化文件，正式寫入前自動備份到 `~/.kinsun/backups/rag/<release>/`，再以新 ID 建候選版；舊 chunks 不會加入 release。禁止使用 `--reset`：

```powershell
$env:PYTHONPATH="src"; uv run python -m kinsun.rag.migrate --in-place --dry-run
$env:PYTHONPATH="src"; uv run python -m kinsun.rag.migrate --in-place
```

`--dry-run` 不建立 schema、不建立備份、不寫資料庫。正式原地遷移的備份為保留舊 `document_id`、URL、文字與 hash 原值的 gzip JSONL，旁附 SHA-256 manifest；備份失敗就中止。ANSWER 文件會重新清洗、700 字切塊與 embedding；DISCOVERY 文件只保存版本 membership 與稽核，不建立回答向量。中止或失敗 release 中已原子完成、模型與結構皆相容的文件可供下版重用，最終仍須重新通過完整 golden set 與發布閘門。

若來源與目標是不同資料庫，則不加 `--in-place`，並設定唯讀來源 `RAG_SOURCE_DATABASE_URL` 與目標 `DATABASE_URL`；兩個連線不得指向同一資料庫。

匯入期末展示 seed：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl
```

```powershell
$env:PYTHONPATH="src"; uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl
```

啟動大型 crawler：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.ingest --max-pages 20 --delay 2 --embedding-delay 6 --embedding-retries 5
```

```powershell
$env:PYTHONPATH="src"; uv run python -m kinsun.rag.ingest --max-pages 20 --delay 2 --embedding-delay 6 --embedding-retries 5
```

免費 Gemini 額度建議使用上述保守設定；預設值也已採同樣策略。`--embedding-delay` 只能處理每分鐘限制，不能突破每日額度。額度用盡時 release 會維持 failed，待額度恢復或方案提高後重跑即可重用已完成文件，不得降低品質閘門。也可在 `.env` 固定設定：

```dotenv
RAG_CRAWLER_MAX_PAGES=20
RAG_CRAWLER_DELAY_SECONDS=2
RAG_EMBEDDING_DELAY_SECONDS=6
RAG_EMBEDDING_TIMEOUT_SECONDS=60
RAG_EMBEDDING_BATCH_SIZE=20
RAG_EMBEDDING_RETRIES=5
RAG_EMBEDDING_RETRY_INITIAL_DELAY_SECONDS=30
RAG_EMBEDDING_RETRY_MAX_DELAY_SECONDS=300
RAG_CONTENT_POLICY=allowed_only
RAG_EMBEDDING_MODEL=gemini-embedding-001
RAG_REFRESH_ENABLED=true
RAG_REFRESH_CRON=0 3 * * 0
RAG_AUDIT_RETENTION_DAYS=90
```

`RAG_CONTENT_POLICY=classroom_demo` 只適用非商用課堂展示；Admin 會持續顯示授權警告。正式或公開環境必須維持 `allowed_only`。

獨立週更 Worker（只重抓 active 版本的已知 URL；RSS／API 新發現只留稽核）：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.worker
PYTHONPATH=src uv run python -m kinsun.rag.worker --once
```

Worker 使用專用的最小設定載入器，只要求資料庫、Gemini、時區、排程與 RAG 相關環境變數；不依賴 LINE、LIFF、ASR、TTS 或音檔設定。線上檢索會先拒絕明顯屬於天氣預報、股價、食譜、即時新聞或過期規定的範圍外問題，再執行向量／中文關鍵字聯集檢索。

2026-07-18 個人 Supabase 原地升級驗收已發布 `rag-20260718T055933Z`：790 份文件、2,808 個 chunks，門檻 0.65，supported top-3 recall 100%、unsupported false-positive 0%、安全案例 100%、citation correctness 90%，且重複 URL、孤兒、空 embedding 與超長 chunk 均為 0。

Release 管理：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.release_cli list
PYTHONPATH=src uv run python -m kinsun.rag.release_cli rollback <index_version>
PYTHONPATH=src uv run python -m kinsun.rag.release_cli cleanup
```

指定單一來源重建：

```bash
PYTHONPATH=src uv run python -m kinsun.rag.ingest --reset --source hpa_elder_health --max-pages 30
```

```powershell
$env:PYTHONPATH="src"; uv run python -m kinsun.rag.ingest --reset --source hpa_elder_health --max-pages 30
```

## 家屬端 LIFF（開發 / 部署）

家屬端網頁採 React + Vite + TypeScript，置於 [`frontend/`](frontend/)，由後端 FastAPI 同源供應於 `/liff`。

### 開發
1. 後端：`uv run uvicorn --app-dir src "kinsun.app:build_app" --factory --reload --port 8000`
2. 前端：`npm --prefix frontend install` 後 `npm --prefix frontend run dev`（dev 會把 `/api` proxy 到本機後端）。
3. 在 `frontend/.env` 填 `VITE_LIFF_ID`（複製自 `frontend/.env.example`）。

### 部署
1. `npm --prefix frontend install && npm --prefix frontend run build` 產出 `frontend/dist`，後端才會供應 `/liff`。
2. 在 LINE Developers 建一個與 Messaging API **同 provider** 的 LINE Login channel + LIFF app，endpoint 指向 `https://<host>/liff`。
3. 後端 `.env` 設 `LIFF_CHANNEL_ID`（該 Login channel ID）；前端 `VITE_LIFF_ID` 設 LIFF ID。

### 家屬圖文選單（Rich Menu，可選）

讓已綁定家屬在 LINE 底部有「開啟家屬儀表板」按鈕。

1. 準備一張選單圖（2500×843、≤1MB、png/jpeg）。
2. 佈建（對真 LINE 執行一次）：
   ```bash
   LINE_CHANNEL_ACCESS_TOKEN=... LIFF_ID=<你的 LIFF ID> \
   PYTHONPATH=src uv run python -m kinsun.channels.line.richmenu <image_path>
   ```
   會印出 `rich_menu_id`。
3. 把它設為後端環境變數 `RICH_MENU_ID`。之後家屬一綁定（建立長輩或兌換家屬邀請碼）即自動獲得選單。
   `RICH_MENU_ID` 未設則此功能停用、綁定照常。
