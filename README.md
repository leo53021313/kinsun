# 金孫 KinSun

> 聽懂國台語的長輩 AI 語音陪伴守護 Agent。

AIPE03 第五組期末專案。

## 專案文件

| 文件 | 內容 |
|------|------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | 多人協作流程（分支、PR、合併規則）— **開始開發前必讀** |
| [AGENTS.md](AGENTS.md) | 開發規範（程式碼品質、安全性、測試…），所有 AI 代理共用 |
| [docs/](docs/) | 專案提案與進度報告 |

## 開發團隊

7 人協作，採「每人一分支 + 整合負責人」模型，整合負責人為 Leo（@leo53021313）。
詳見 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 快速開始

> 專案目錄骨架待架構定案後補上；以下為開發環境設定。

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

## 啟動本機開發（第一刀薄切片）

第一刀是「LINE 收語音 → ASR → Care Agent → Gemini → 文字回覆」的端到端薄切片。
詳細設計見 [docs/superpowers/specs/](docs/superpowers/specs/)，實作計畫見 [docs/superpowers/plans/](docs/superpowers/plans/)。

1. 複製 `.env.example` 為 `.env`，填入 LINE 與 Gemini 憑證（ASR 先用 `mock`，不需 GPU）。
2. 啟動 webhook：

   ```bash
   uv run uvicorn --app-dir src "kinsun.app:build_app" --factory --reload --port 8000
   ```

3. 用 ngrok 之類工具把 `https://<你的網域>/line/webhook` 設為 LINE 的 Webhook URL。
4. 對 LINE 官方帳號傳語音訊息，即可收到金孫回覆（dev 期 ASR 為 mock 文字）。

> 真實 ASR：在 DGX 啟動 `services/asr`，並把 `.env` 改為 `ASR_BACKEND=dgx`、`ASR_ENDPOINT=http://<dgx>:8001/transcribe`。

執行測試（不需 GPU、不需憑證）：

```bash
uv run pytest
```
