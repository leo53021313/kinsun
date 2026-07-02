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

執行測試（全離線、不需 GPU/金鑰；雲端整合測試需 `KINSUN_IT=1` + 真金鑰才會跑）：

```bash
uv run pytest
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
