# 金孫 KinSun — 開發進度與注意事項

> 聽懂國台語的長輩 AI 語音陪伴守護 Agent（AIPE03 第五組）。
> 本檔為**進度快照**，最後更新：2026-06-29。規範請見 [AGENTS.md](AGENTS.md)（唯一真實來源）。

---

## 1. 系統概觀

長輩用 **LINE 語音**跟「金孫」聊天 → ASR 轉文字 → 危急偵測 + Care Agent（Gemini）回應 → TTS 回覆；
背景有長期記憶、每日整理、主動關懷、危急時通知家屬。模組以 **Protocol 介面**解耦，可抽換（mock ↔ 真模型、SQLite ↔ 雲端）。

**端到端流程：**
```
LINE 語音 → webhook → VoicePipeline
   ├─ ASR（mock，待接 DGX）→ 文字
   ├─ RiskDetector（Gemini 分級 L0–L3）→ tier≥L2 → LineGuardianNotifier 推播家屬
   ├─ CareAgent（Gemini + 短期/長期記憶）→ 回覆
   └─ TTS（文字泡泡 placeholder，待接台語 TTS）
排程 worker：每日記憶整理、定時問候、失聯關心
```

---

## 2. 技術棧與環境

| 項目 | 選型 |
|------|------|
| 語言/工具 | Python 3.12、**uv**、ruff（E,W,F,I,B,UP / line-length 100）、pre-commit、pytest |
| 對外 | FastAPI webhook、line-bot-sdk v3 |
| LLM/Embedding | Gemini：`gemini-3.1-flash-lite`（對話/分級/抽取）、`gemini-embedding-001` |
| 長期記憶 | **Mem0** v1.1 新演算法（單次抽取＋entity linking＋語意/BM25/entity 多訊號檢索）＝ Supabase Postgres（pgvector） |
| 短期記憶/帳號 | **Supabase Postgres**（`psycopg` v3） |
| 佈署目標 | **NVIDIA DGX Spark**（Linux + ARM64/aarch64），同時是開發環境 |

**跨平台紀律（Windows / macOS / DGX Spark 三邊都要能跑）：**
- OS-agnostic：用 `pathlib`，不寫死路徑；設定/金鑰走環境變數。
- ARM64 相容：新依賴須在 `linux/aarch64` 有 wheel；吃 GPU 的重模型（ASR/TTS）只跑 DGX。
- 位置無關：重模型走可設定 endpoint（環境變數），同機/分離都不改程式。
- `tzdata` 為依賴（修正 Windows 無 `Asia/Taipei` 時區的問題）。

> ⚠️ **雲端遷移後，啟動 app 一定要雲端金鑰**（`DATABASE_URL`、`GEMINI_API_KEY`、LINE）。
> 本機已無 SQLite，無法離線跑整支 app；但**單元測試全離線**（注入 fake，不需網路/金鑰）。

---

## 3. 已完成模組

| # | 模組 | 內容 | PR |
|---|------|------|-----|
| 1 | 端到端語音薄切片 | ASR(mock)→Agent→TTS(泡泡)、LINE webhook、組裝根 app.py | — |
| 2 | 短期記憶 | `MemoryStore` Protocol；今日對話、`max_turns`、`last_active` | — |
| 3 | 危急偵測核心 | `RiskTier` L0–L3、關鍵字 + Gemini 分級、`RiskDetector`（fail-safe、絕對危險詞覆蓋） | — |
| 4 | 記憶層雲端遷移 | Mem0＋Supabase pgvector 取代自建 SQLite（註：原規劃的 Neo4j graph 經實測 mem0 2.0.10 不支援，已於 MEM-UP 移除，關係感知改靠 v1.1 entity linking／多訊號檢索） | #14 |
| 5 | 排程引擎 | `Scheduler`（每日一次、錯誤隔離）、worker 常駐 | — |
| 6 | 主動關懷 | 定時問候 + 失聯關心 job（共用排程器、走 CareAgent + 記憶） | — |
| 7 | 帳號綁定核心 | 5 實體 + `PgAccountRepository` + `AccountService`（建檔/邀請/兌換/同意/家屬清單/權限） | #12 |
| 8 | 危急真實家屬通知 | `LineGuardianNotifier`：tier≥L2 → 查 `guardian_line_ids` → 依升級順序 push 全部家屬 | #15 |

**測試現況：** `uv run pytest` → 86 passed、3 skipped（雲端整合 opt-in，需 `KINSUN_IT=1`）；89 收集。ruff/format/pre-commit 全綠。

---

## 4. 程式結構（src/kinsun/）

```
app.py              組裝根（settings → 各元件 → FastAPI app）
config.py / db.py   設定（環境變數）／Postgres 連線 + 建表 DDL
llm.py              GeminiClient、Message
agent.py            CareAgent（金孫 persona + 安全邊界）
pipeline.py         VoicePipeline（ASR→偵測→Agent→通知→TTS）
recall.py           MemoryContext（包 LongTermStore.search）
speech/             asr.py（mock/DGX 可切）、tts.py（文字泡泡）
channels/line/      webhook.py、messenger.py（get_audio/reply_text/push_text）
safety/             tiers/keywords/classifier/detector/notifier
memory/             PgMemoryStore（短期）
longterm/           Mem0LongTermStore、provenance、consolidation
scheduler/          Scheduler、jobs、worker
proactive/          問候 + 失聯 job
accounts/           models、PgAccountRepository、AccountService
```

> 🧹 小清理：`knowledge/`、`episodic/` 為雲端遷移後留下的空目錄，可刪。

---

## 5. 開發工作流（每模組）

```
brainstorm（談清楚、設計通過才動工）
  → spec（docs/superpowers/specs/）→ commit
  → 計畫（docs/superpowers/plans/，bite-sized TDD）→ commit
  → TDD 實作（每步 紅→綠→commit）
  → 品質閘門（pytest / ruff / format / pre-commit 全綠）
  → push → PR → 合併 → 同步分支
```

**核心原則：** 正確性優先、最小修改、不臆測（資訊不足先問）、全程 fail-safe（記憶/LLM/DB 失敗都退化、不中斷對話）、依賴注入時鐘/亂數以利 TDD、無必要不加第三方套件。

---

## 6. Git 與協作（7 人，每人一分支 + 整合負責人）

- 只在**個人分支**（本機為 `Leo`）工作；`main` 受保護，僅經 PR 合併。
- commit 規範：`feat/fix/docs/refactor/test/chore`，結尾加
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- **不自動 push**（等明確指示）、**不改寫 Git 歷史**（rebase/force push）。
- 合併後同步 `main` 到各成員分支：`git push origin origin/main:<branch>`。

> ⚠️ **分支同步注意：** `Jerry` 分支有自己未合併的提交（「衛教 RAG 資料治理與安全閘門」），FF 同步會被拒（non-fast-forward）。
> **不可強推覆蓋**——由 Jerry 自行把 `main` 合併進去。其餘 Babic/Brian/Kevin/MA/Otto 可正常 FF 同步。

---

## 7. 待開發模組（候選）

| 群組 | 模組 | 備註 |
|------|------|------|
| **A. 綁定入口** ⭐ | 長者/家屬端綁定流程（LINE 引導式對話）、綁定閘門 | **解鎖危急通知/用藥提醒**；目前 `AccountService` 無使用者入口 |
| B. 照護功能 | 用藥提醒（accounts + scheduler 已備） | — |
| | 衛教 RAG / 工具 | ⚠️ **Jerry 進行中**，避免撞車 |
| C. 真模型接 DGX | 真 ASR 整合（現 mock）、真台語 TTS（現文字泡泡） | 重、跨 DGX |
| D. 安全/治理 | 危急通知 v2（升級鏈/ack/多通道/節流）、對話安全 3 議題 | 見策略文件 |

**策略/待議文件：**
[危急偵測與誤報處理設計](docs/危急偵測與誤報處理設計.md)、
[帳號綁定與知情同意設計](docs/帳號綁定與知情同意設計.md)、
[對話安全與資料正確性-待議](docs/對話安全與資料正確性-待議.md)（情感依賴 / 身體vs心理歸因 / 健康宣稱 provenance）。

---

## 8. 進行中：長者/家屬端綁定流程（規劃中，尚未實作）

**已鎖定決策（brainstorming）：**
- 範圍：**只做綁定指令入口**（綁定閘門另案）。
- 互動：**引導式對話**（狀態機，存每人未完成流程）。
- 啟動：單一關鍵字 **「設定」** + 數字選單（1 建立長輩 / 2 邀請家屬 / 3 綁定貼碼）；**貼碼自動辨識**。
- 狀態存 Postgres 新表 `binding_sessions`（behind Protocol + fake）；逾時重置。
- 知情同意於確認步驟顯示，`consent_by=SELF`；代理同意 PROXY 不在 v1。
- 全 fail-safe；非綁定文字回 None → 維持既有語音提示。

**待定（下次確認）：**
- (a) 流程 2「邀請家屬」是否留在 v1（拿掉則只剩主家屬一人）。
- (b) 家屬姓名是否真抓 LINE 暱稱（不抓則存空字串，可省 `messenger.display_name`）。

> 確認後流程：spec → 計畫 → TDD 實作（同既有工作流）。
