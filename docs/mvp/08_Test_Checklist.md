# 08 Test Checklist — 金孫 KinSun

> **文件性質**：依 2026-07-06 程式碼現況反向盤點的測試地圖與檢查清單。
> 真整合逐功能驗收表**已存在**於 [功能實測驗收清單](../功能實測驗收清單.md)（A–E 區，含分工），
> 本文件不重複它，而是補上：測試分層全貌、跑法、缺口、與發布閘門。
> ⚠️ 標記者對應 [全庫人工決策盤點-待議](../全庫人工決策盤點-待議.md)。

---

## 1. 測試分層與現況

| 層 | 內容 | 怎麼跑 | 現況（2026-07-06） |
|----|------|--------|--------------------|
| 離線單元測試 | 76 個測試檔，全部注入 fake，不需網路／金鑰 | `uv run pytest` | ✅ 430 passed／42 skipped，<3 秒 |
| Store 合約測試 | 同一份斷言參數化跑 Fake＋Pg，共 **10 個領域**（accounts、appointments、binding_session、medications、memory_shortterm、observability、reports_reminders、reports_summaries、safety_events、scheduler_state） | Fake 半：隨 pytest；Pg 半：`KINSUN_IT=1 uv run pytest` | ✅ Fake 全綠；Pg 半即 42 個 skipped |
| 雲端整合測試 | `test_pg_*.py`＋合約 Pg 半，連真 Supabase | `KINSUN_IT=1`＋`DATABASE_URL` | ⬜ 需真金鑰，CI 不跑 |
| 真整合實測 | LINE／Gemini／mem0／DGX 真串接 | 人工，依 [功能實測驗收清單](../功能實測驗收清單.md) | ⬜ **A–E 區全數未測** |
| Lint／格式 | ruff（E,W,F,I,B,UP／line-length 100）＋pre-commit | `uv run ruff check .`／`uv run ruff format .` | ✅ 全綠 |
| 前端 | typecheck＋build | `npm run typecheck`／`build`／`build:admin` | ✅ CI 有跑 |
| CI | `.github/workflows/ci.yml`：main 的 PR 與 push | 自動 | ✅ test job＋frontend job |

**最重要的一句話**（progress.md §9 的教訓）：**綠燈 ≠ 真整合可行**。
全部單元測試都是離線 fake，驗不到 LINE／Gemini／Supabase／mem0／DGX 真串接；
首次真雲端啟動時就曾抓出 7 個離線測試看不到的整合問題。

## 2. 指令速查

```bash
uv run pytest                          # 離線全套（<3 秒）
KINSUN_IT=1 uv run pytest              # 含 Pg 整合（需 DATABASE_URL 真金鑰）
uv run ruff check . && uv run ruff format --check .   # lint＋排版檢查
npm --prefix frontend run typecheck    # 前端型別檢查
```

- pytest 設定：`pyproject.toml` `[tool.pytest.ini_options]`（testpaths=tests、pythonpath=src）。
- `KINSUN_` 前綴保留給測試／CI 旗標（AGENTS.md）。
- 後端**無 mypy／型別檢查**，型別檢查僅前端有。

## 3. 已知測試缺口（盤點結果）

**完全沒有對應測試檔的模組**：

| 模組 | 風險 |
|------|------|
| `rag/document_loader.py`、`rag/ingest.py`、`rag/reranker.py`、`rag/text_cleaner.py` | RAG 子系統缺口最大（Jerry 分支進行中）⚠️ T-50 |
| `scheduler/worker.py`、`scheduler/__main__.py` | 排程執行層——worker 掛掉＝所有提醒靜默停止 ⚠️ E-17 |
| `observability/models.py` | 低風險（純資料結構） |

**只有間接覆蓋**：`app.py`（靠 TestClient）、`channels/line/messenger.py`、
`rag/citation.py`／`keyword_index.py`／`schemas.py`／`source_registry.py`、`tools/health_rag.py`。

**測試策略層級的缺口**（不是單一檔案問題）：

- 排程 job 無手動觸發 CLI，實測只能改鐘點＋重啟 worker（見驗收清單 C 區說明）。
- 台語語音與國語詞表的銜接從未實測 ⚠️ T-13。
- 語音回覆從未在真 LINE 上驗證可播放 ⚠️ T-41。
- 危急偵測無「判準正確性」評測集：現有測試驗的是接線邏輯，不是「這句話該不該算 L2」⚠️ T-02～T-04。

## 4. 發布前檢查清單（Go-live Gate）

> 依老師指南 §13：「要正式上線」的最低必要文件是 Deployment Guide、Release Checklist、Runbook。
> 部署步驟現況已寫在 [功能實測驗收清單 §1 環境啟動 Runbook](../功能實測驗收清單.md)；以下為發布閘門。

- [ ] `uv run pytest` 全綠、`ruff check`／`format --check` 全綠、CI 綠
- [ ] `KINSUN_IT=1` Pg 整合測試全綠（對真 Supabase）
- [ ] [功能實測驗收清單](../功能實測驗收清單.md) A–E 區全數 ✅（F 區 RAG 由 Jerry 分支獨立驗）
- [ ] 待議清單 **24 項 P0** 逐項有決議（修正、或明文接受風險並記錄誰拍板）
- [ ] 危急偵測誤報／漏報評測集建立並跑過一輪（T-02～T-04 拍板後）
- [ ] 成本試算完成：LINE push 配額＋Gemini 月成本 ⚠️ T-51
- [ ] DGX ASR／TTS 服務加上認證或網路隔離 ⚠️ T-49
- [ ] 金孫參考語音定調＋聲音授權確認 ⚠️ T-39
- [ ] 監控告警：scheduler worker 存活監控 ⚠️ E-17

## 5. 測試撰寫慣例（給新測試）

- 檔名 `test_<套件>_<檔>.py`；連 Postgres 的整合測試獨立成 `test_pg_<套件>_<檔>.py`。
- 一個 seam 兩個 adapter 的等價合約用 `test_<領域>_store_contract.py`，
  `Fake<領域>Store` 與 Protocol＋Pg 同住 `store.py`，`tests/fakes.py` 僅匯入轉出。
- 依賴注入時鐘／亂數以利 TDD；fail-safe 分支（記憶／LLM／DB 失敗）必須有測試。
- 完整規範見 [AGENTS.md](../../AGENTS.md)。
