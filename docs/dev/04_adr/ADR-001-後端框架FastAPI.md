# ADR-001: 後端框架採 Python＋FastAPI，環境以 uv 管理

> **狀態:** 已接受 | **日期:** 2026-07-08 | **決策者:** Leo（批次重新確認）

## 1. 背景與問題

- **上下文**: 後端需承載 LINE webhook、App REST API、排程 worker、LLM／語音管線；團隊 7 人多為非本科、以 AI 工具輔助開發。
- **問題**: 需要一個生態成熟、非同步友善、與 AI 產碼相容性高的後端框架。
- **驅動因素/約束**: 跨平台（Windows／macOS／DGX ARM64）；AGENTS.md 已規範 uv 統一環境。

## 2. 考量的選項

- **FastAPI**：非同步原生、Pydantic 驗證、依賴注入；生態大。
- **Flask／Django**：同步為主（Flask）或過重（Django admin/ORM 用不到）。

## 3. 決策

**選擇**: FastAPI＋uvicorn（`build_app()` 工廠模式，`src/kinsun/app.py:42`），uv 管依賴。

**理由**: 現有 344 個測試綠燈、四個部署單元皆已就位；語音管線需要 async；無任何改動收益。

## 4. 後果

- **正面**: Pydantic 邊界驗證與 AGENTS.md 輸入驗證規範天然契合。
- **負面**: 無顯著。
- **重新評估觸發**: 出現 FastAPI 無法支撐的長連線／串流需求（如即時語音串流）時。
