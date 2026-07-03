# 命名一致性盤點與統一——實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全面盤點專案五個面向的命名分歧，經使用者逐項核可後，一次性統一全專案命名並通過全測試。

**Architecture:** 三階段流程——（1）五個平行探索代理各盤點一個面向，彙整成《命名決策表》；（2）使用者逐項核可，未核可項目不動；（3）依五個批次（檔案模組 → 識別字 → API → 環境變數 → DB Schema）由低風險到高風險執行改名，每批次一個 commit、全測試通過才進下一批。

**Tech Stack:** Python 3.12（src layout，uv 管理）、pytest、Vite + TypeScript（frontend/）、SQLite/Supabase（Schema 定義於 `src/kinsun/db.py`）。

**設計文件：** `docs/superpowers/specs/2026-07-03-naming-consistency-design.md`（已核可，本計畫的唯一需求來源）。

## Global Constraints

- 一律使用台灣繁體中文與全形標點（回覆、文件、註解、commit 訊息）。
- 只在 `Leo` 分支工作；**不自動 push**；不改寫 Git 歷史。
- commit 訊息遵循 CONTRIBUTING.md 前綴（本計畫的改名一律用 `refactor:`，文件用 `docs:`）。
- 不新增第三方套件；不做與命名無關的重構或格式調整。
- 測試基準：`uv run pytest -q` 目前為 **308 passed, 12 skipped**；每批次結束必須 0 failed。
- frontend 建置：`cd frontend && npm run build`（tsc --noEmit + vite build）必須成功。
- DB 為開發階段、資料可丟：改 Schema **不寫遷移腳本**。
- **禁止盲目全域取代**：每個舊名出現處都要確認語意（同名不同義處跳過並記錄於決策表備註）。
- 未經使用者核可的命名項目一律不動。

---

### Task 1: 前置與基準確立

**Files:**
- 不修改任何程式檔（僅 Git 操作與驗證指令）。

**Interfaces:**
- Produces: 乾淨的工作區（無未提交變更）＋記錄在案的測試基準數字，供後續所有批次比對。

- [ ] **Step 1: 詢問使用者如何處理未提交變更**

工作區現有 `src/kinsun/channels/inbound.py` 與 `tests/test_inbound.py` 未提交變更（先以 `git status --short` 確認仍存在）。以 AskUserQuestion 詢問使用者：「先提交」或「暫存（git stash）」。此步驟必須由主會話（orchestrator）執行，不可交給子代理。

- [ ] **Step 2: 依使用者決定清空工作區**

若選「先提交」：請使用者確認 commit 訊息意圖後執行（變更內容與語音回覆功能相關，預設訊息 `feat: inbound 語音處理調整（改名前先行提交）`，實際訊息依 diff 內容與使用者確認為準）。
若選「暫存」：執行 `git stash push -m "改名前暫存：inbound 語音調整"`。
完成後執行：

```bash
git status --short
```

Expected: 無輸出（工作區乾淨）。

- [ ] **Step 3: 確立測試與建置基準**

```bash
uv run pytest -q 2>&1 | tail -1
cd frontend && npm run build 2>&1 | tail -3; cd ..
```

Expected: pytest 顯示 `308 passed, 12 skipped`（若因 Step 2 提交而略有增減，記下實際數字作為新基準）；frontend 建置成功（vite build 輸出 `✓ built`）。若基準測試有 failed，**停止計畫**並回報使用者——不能在紅燈上做大規模改名。

---

### Task 2: 五面向平行盤點

**Files:**
- 不修改任何檔案（唯讀盤點）。

**Interfaces:**
- Produces: 五份分歧清單（每份為 markdown 條列，含：分歧概念、各種現況寫法、每種寫法的出現處數與代表檔案、初步建議統一名與理由），供 Task 3 彙整。

- [ ] **Step 1: 平行派出五個唯讀探索代理（單一訊息、五個 Agent 呼叫，subagent_type=Explore，搜尋廣度=very thorough）**

五個代理的提示詞如下（各自獨立、完整自足）：

**代理 A——程式識別字：**
> 唯讀盤點 /home/leo29/kinsun 的 src/、tests/、services/ 中 Python 程式碼「同概念異名」的識別字（變數、函式、類別、方法、參數）。已知例子：elder_id 與 user_id 並存（釐清兩者是同一概念還是不同概念——elder 是長輩、user 可能是 LINE 使用者，若語意不同請明說）。另請系統性檢查：資料存取層命名（store／repository／dao）、服務層命名（service／manager／handler）、動詞用法（get／fetch／load／query；create／add／insert；handle／process／dispatch）、布林命名（is_／has_／enable_／enabled）、時間欄位（created_at／create_time 等）。每項分歧列出：概念說明、各寫法與出現處數（用 grep 統計）、代表檔案路徑、你建議的統一名與一句話理由。以 markdown 條列回傳，不要修改任何檔案。

**代理 B——環境變數與設定：**
> 唯讀盤點 /home/leo29/kinsun 的環境變數與設定鍵命名一致性。來源：.env.example（41 個鍵）、src/kinsun/config.py、services/asr 與 services/tts 底下所有讀取環境變數之處（搜 os.environ、os.getenv、getenv）、docs/ 與 README.md 中提及的環境變數。檢查：前綴風格是否一致（有無 KINSUN_ 之類前綴、TTS_／ASR_ 前綴用法）、同一設定在程式與 .env.example 中名稱是否吻合、config.py 的欄位名與環境變數名的對應規則是否一致、有無「程式讀了但 .env.example 沒列」或反之的孤兒鍵。每項分歧列出：鍵名、出現位置（檔案:行）、建議統一名與理由。以 markdown 條列回傳，不要修改任何檔案。

**代理 C——檔案與模組命名：**
> 唯讀盤點 /home/leo29/kinsun 的 src/kinsun/ 各子模組、services/、tests/、frontend/src/ 的檔案與目錄命名一致性。已知例子：jobs.py 同時存在於 proactive/ 與 scheduler/；longterm/store.py 與 accounts/repository.py 是否為同層概念但異名。檢查：同角色檔案的命名慣例（models／schemas、store／repository、service、api／routes）、模組名單複數、目錄命名（longterm 這種連寫 vs 其他風格）、tests/ 測試檔名是否與被測模組一一對應（test_<module>.py）。每項分歧列出：涉及路徑、建議統一名（含改名後的完整路徑）與理由、改名會影響的 import 數量（用 grep 統計）。以 markdown 條列回傳，不要修改任何檔案。

**代理 D——API 路由與欄位：**
> 唯讀盤點 /home/leo29/kinsun 的 web API 命名一致性。來源：src/kinsun/web/api.py 與 web/auth.py（路由路徑、路徑參數、查詢參數、請求／回應 JSON 欄位）、frontend/src/ 中呼叫這些 API 的程式碼（搜 fetch、axios、路徑字串）。檢查：路徑風格（單複數、kebab-case vs snake_case）、JSON 欄位命名風格（snake_case vs camelCase）是否前後端一致、同一資源在不同端點的欄位名是否一致（例如 elder_id 在 A 端點、user_id 在 B 端點）。每項分歧列出：端點與欄位、前端對應使用處（檔案:行）、建議統一名與理由。以 markdown 條列回傳，不要修改任何檔案。

**代理 E——DB Schema：**
> 唯讀盤點 /home/leo29/kinsun 的資料庫 Schema 命名一致性。來源：src/kinsun/db.py 的所有 CREATE TABLE 陳述式，以及各模組中撰寫 SQL 的地方（grep 搜 SELECT、INSERT、UPDATE、DELETE、FROM）。檢查：資料表命名（單複數、風格）、欄位命名（elder_id vs user_id、時間欄位 created_at 風格、外鍵命名 <table>_id 慣例）、同概念欄位跨表是否同名、程式端模型欄位（accounts/models.py 等）與資料表欄位是否對齊。每項分歧列出：表名／欄位名、出現位置、建議統一名與理由、涉及的 SQL 陳述式數量。以 markdown 條列回傳，不要修改任何檔案。

- [ ] **Step 2: 收齊五份清單並檢查完整性**

確認五份回報都包含「寫法、處數、建議名、理由」四要素；缺漏者以 SendMessage 請該代理補齊。特別確認代理 A 對 elder_id／user_id 是「同概念異名」還是「不同概念」的判定，這是最大宗（229＋110 處），會直接影響決策表建議。

---

### Task 3: 彙整《命名決策表》並提交

**Files:**
- Create: `docs/superpowers/specs/2026-07-03-naming-decisions.md`

**Interfaces:**
- Consumes: Task 2 的五份分歧清單。
- Produces: 供使用者核可的決策表；表中每列的「編號、面向、建議統一名」是 Task 5–9 的執行輸入。

- [ ] **Step 1: 撰寫決策表**

以下列格式彙整（一列一個分歧點，依面向分五節；同節內按影響處數由大到小排）：

```markdown
# 命名決策表（2026-07-03）

> 核可方式：回覆「全部照建議」，或指定「#N 改成 xxx」「#N 不改」。
> 「決議」欄由使用者核可後填入；未填「核可」的列一律不動。

## 一、程式識別字

| # | 概念 | 現況寫法（處數） | 建議統一名 | 理由 | 影響範圍 | 決議 |
|---|------|------------------|------------|------|----------|------|
| 1 | 長輩識別碼 | elder_id（229）／user_id（110） | （依盤點結果填入） | （一句話） | src＋tests＋db＋api | （待核可） |

## 二、環境變數與設定
（同格式）

## 三、檔案與模組命名
（同格式，「建議統一名」填改名後完整路徑）

## 四、API 路由與欄位
（同格式，另加「前端同步處」欄）

## 五、DB Schema
（同格式）

## 附錄：需人工同步的項目
- DGX 實際 `.env`：（列出核可後需手動改的鍵，舊名 → 新名）
- 其他不在版控內的部署設定：（如 ngrok、webhook 設定，若有）
```

注意：若某分歧經盤點判定是「不同概念、名稱本來就該不同」（例如 elder 與 LINE user 若真是兩回事），仍要列入表中，建議填「不改（不同概念）」，讓使用者知情確認。

- [ ] **Step 2: 提交決策表**

```bash
git add docs/superpowers/specs/2026-07-03-naming-decisions.md
git commit -m "docs: 命名決策表（五面向盤點結果，待核可）"
```

Expected: commit 成功，僅含此一檔案。

---

### Task 4: 使用者逐項核可（GATE——未通過不得進入 Task 5）

**Files:**
- Modify: `docs/superpowers/specs/2026-07-03-naming-decisions.md`（填入決議欄）

**Interfaces:**
- Produces: 每列「決議」欄為「核可（名稱）」或「不改」的最終決策表，Task 5–9 只執行決議＝核可的列。

- [ ] **Step 1: 向使用者呈現決策表摘要並請其核可**

在對話中列出決策表全部項目（編號＋建議名＋一句理由），請使用者回覆「全部照建議」或逐項指定。此步驟必須由主會話執行。

- [ ] **Step 2: 將決議寫回決策表並提交**

依使用者回覆填入每列「決議」欄，然後：

```bash
git add docs/superpowers/specs/2026-07-03-naming-decisions.md
git commit -m "docs: 命名決策表填入使用者決議"
```

Expected: commit 成功。若使用者對任何項目提出新名稱，以使用者版本為準。

---

### Task 5: 批次一——檔案與模組改名

**Files:**
- Modify: 決策表「三、檔案與模組命名」中決議＝核可的所有路徑，及其所有 import 引用處（src/、tests/、services/、docs/）。

**Interfaces:**
- Consumes: Task 4 決策表第三節核可列（舊路徑 → 新路徑對照）。
- Produces: 新模組路徑；後續批次的 grep 與修改以新路徑為準。

- [ ] **Step 1: 逐項執行 git mv 並修全部 import**

對每個核可列：

```bash
git mv <舊路徑> <新路徑>
grep -rn "<舊模組名>" src/ tests/ services/ docs/ README.md --include="*.py" --include="*.md"
```

逐處把 import 與文件引用改成新名。對應的測試檔若因模組改名而不再對應（test_<舊名>.py），一併 `git mv` 成 test_<新名>.py。

- [ ] **Step 2: 殘留檢查**

```bash
grep -rn "<舊模組名>" src/ tests/ services/ frontend/src/ docs/ README.md .env.example | grep -v "docs/superpowers/specs/"
```

Expected: 無輸出（設計文件與決策表中的歷史紀錄除外，已用 grep -v 排除）。

- [ ] **Step 3: 全測試**

```bash
uv run pytest -q 2>&1 | tail -1
```

Expected: 0 failed，passed 數與 Task 1 基準一致。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: 統一檔案與模組命名（批次一，依命名決策表）"
```

---

### Task 6: 批次二——程式識別字改名

**Files:**
- Modify: 決策表「一、程式識別字」中決議＝核可各列涉及的所有 .py 檔（src/、tests/、services/）。**本批次不動** API 對外欄位、環境變數、DB 欄位——那些留給批次三～五（若同一識別字橫跨多面向，本批次只改純內部使用處，跨面向處數記入對應批次）。

**Interfaces:**
- Consumes: Task 4 決策表第一節核可列（舊名 → 新名對照）。
- Produces: 統一後的內部識別字；批次三～五的程式端引用以新名為準。

- [ ] **Step 1: 逐項改名（處數大的項目先做）**

對每個核可列：

```bash
grep -rn --include="*.py" "\b<舊名>\b" src/ tests/ services/
```

逐處確認語意後修改（函式與類別名連同呼叫處、docstring、註解一起改；字串內容若是使用者可見文案或 DB／API 鍵，跳過留給對應批次）。同名不同義處不改，並在決策表該列備註欄記錄「保留處：檔案:行，原因」。

- [ ] **Step 2: 殘留檢查（逐項）**

```bash
grep -rn --include="*.py" "\b<舊名>\b" src/ tests/ services/
```

Expected: 僅剩決策表備註中記錄的「同名不同義」保留處；其餘無輸出。

- [ ] **Step 3: 全測試**

```bash
uv run pytest -q 2>&1 | tail -1
```

Expected: 0 failed，passed 數與基準一致。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: 統一程式識別字命名（批次二，依命名決策表）"
```

---

### Task 7: 批次三——API 路由與欄位（含 frontend 同步）

**Files:**
- Modify: `src/kinsun/web/api.py`、`src/kinsun/web/auth.py`、對應測試（tests/test_api_*.py）、`frontend/src/` 中所有呼叫處、涉及的 docs/。

**Interfaces:**
- Consumes: Task 4 決策表第四節核可列（端點／欄位舊名 → 新名，含前端同步處清單）。
- Produces: 統一後的 API 契約；文件（Task 10）以此為準。

- [ ] **Step 1: 改後端路由與欄位**

對每個核可列，改 `web/api.py`／`auth.py` 的路徑與 JSON 欄位，並同步修改對應測試中的請求路徑與斷言欄位。

- [ ] **Step 2: 同步 frontend**

依決策表「前端同步處」欄逐檔修改 `frontend/src/` 的 API 路徑與欄位存取。

- [ ] **Step 3: 殘留檢查**

```bash
grep -rn "<舊路徑或舊欄位>" src/kinsun/web/ tests/ frontend/src/ docs/
```

Expected: 無輸出（每個核可列各跑一次）。

- [ ] **Step 4: 後端全測試＋前端建置**

```bash
uv run pytest -q 2>&1 | tail -1
cd frontend && npm run build 2>&1 | tail -3; cd ..
```

Expected: pytest 0 failed；frontend `✓ built` 成功（tsc 無型別錯誤）。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 統一 API 路由與欄位命名（批次三，含 frontend 同步）"
```

---

### Task 8: 批次四——環境變數改名

**Files:**
- Modify: `.env.example`、`src/kinsun/config.py`、`services/asr/`、`services/tts/` 讀取處、提及這些鍵的 docs/ 與 README.md。

**Interfaces:**
- Consumes: Task 4 決策表第二節核可列（鍵舊名 → 新名）。
- Produces: 統一後的環境變數鍵；「需人工同步清單」（DGX 實際 .env）成為 Task 11 交付物的一部分。

- [ ] **Step 1: 逐鍵改名**

對每個核可列，同步修改：`.env.example` 的鍵、`config.py` 的讀取名與對應欄位、services/ 下的 getenv 呼叫、文件中的提及處。**同時更新本機 `.env`**（不在版控，直接編輯），否則下一步測試會因讀不到設定而失敗。

- [ ] **Step 2: 殘留檢查**

```bash
grep -rn "<舊鍵名>" src/ tests/ services/ docs/ README.md .env.example .env | grep -v "docs/superpowers/specs/"
```

Expected: 無輸出。

- [ ] **Step 3: 全測試（含服務啟動煙霧測試）**

```bash
uv run pytest -q 2>&1 | tail -1
uv run python -c "from kinsun.config import load_settings; load_settings()"
```

Expected: pytest 0 failed；load_settings() 無例外（若函式名於批次二已改名，用新名）。

- [ ] **Step 4: 更新決策表附錄的人工同步清單**

把本批次實際改動的鍵寫入決策表「附錄：需人工同步的項目」（舊名 → 新名），提醒 DGX 部署環境需手動改。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 統一環境變數命名（批次四，同步 .env.example 與文件）"
```

---

### Task 9: 批次五——DB Schema 改名

**Files:**
- Modify: `src/kinsun/db.py`（CREATE TABLE）、各模組內含 SQL 的檔案、涉及欄位的模型檔（如 `accounts/models.py`）、對應測試。

**Interfaces:**
- Consumes: Task 4 決策表第五節核可列（表／欄位舊名 → 新名）。
- Produces: 統一後的 Schema；開發資料庫直接重建，無遷移腳本。

- [ ] **Step 1: 改 Schema 與所有 SQL**

對每個核可列，修改 db.py 的 CREATE TABLE 與全專案 SQL 字串中的表名／欄位名，及模型欄位、測試斷言。SQL 在字串裡，`\b` 邊界對 grep 仍有效：

```bash
grep -rn --include="*.py" "\b<舊表或欄位名>\b" src/ tests/
```

- [ ] **Step 2: 重建開發資料庫**

刪除本機開發資料庫檔案後重跑 schema 建立（依 db.py 的 ensure_schema 路徑；若使用 Supabase 開發專案，依決策表附錄記錄需在 Supabase 端手動重建的表）。

- [ ] **Step 3: 殘留檢查與全測試**

```bash
grep -rn --include="*.py" "\b<舊表或欄位名>\b" src/ tests/ services/
uv run pytest -q 2>&1 | tail -1
```

Expected: grep 無輸出；pytest 0 failed。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: 統一 DB Schema 命名（批次五，開發庫直接重建）"
```

---

### Task 10: 命名規範入 AGENTS.md 與文件總同步

**Files:**
- Modify: `AGENTS.md`（新增「命名規範」一節）、README.md、docs/ 中仍殘留舊名的文件。

**Interfaces:**
- Consumes: Task 4 決策表全部核可決議。
- Produces: 固化的命名規範，供日後所有開發遵循。

- [ ] **Step 1: 在 AGENTS.md 新增「命名規範（Naming Conventions）」一節**

內容由決策表核可結果歸納，至少涵蓋：核心領域名詞的正名（如長輩識別碼統一用哪個）、資料存取層與服務層檔名慣例、環境變數前綴規則、API 路徑與 JSON 欄位風格、DB 表與欄位慣例。每條規則一行，附一個正例。

- [ ] **Step 2: 全文件殘留掃描**

```bash
grep -rn "<各舊名>" docs/ README.md CONTEXT.md progress.md | grep -v "docs/superpowers/specs/"
```

Expected: 無輸出；有則逐處更新。

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: 命名規範入 AGENTS.md 並同步全文件"
```

---

### Task 11: 最終驗證與總結

**Files:**
- 不新增修改（驗證與回報）。

**Interfaces:**
- Consumes: Task 5–10 的全部改動。
- Produces: 給使用者的完成報告與人工同步清單。

- [ ] **Step 1: 完整驗證**

```bash
uv run pytest -q 2>&1 | tail -1
cd frontend && npm run build 2>&1 | tail -3; cd ..
git log --oneline -8
```

Expected: pytest 0 failed；frontend 建置成功；log 顯示批次一～五＋文件 commit 序列完整。

- [ ] **Step 2: 全域舊名終掃**

對決策表所有核可列的舊名各跑一次：

```bash
grep -rn "\b<舊名>\b" src/ tests/ services/ frontend/src/ docs/ README.md .env.example | grep -v "docs/superpowers/specs/"
```

Expected: 僅剩決策表備註記錄的「同名不同義」保留處。

- [ ] **Step 3: 向使用者總結**

回報：各批次改動摘要（項目數、檔案數）、測試結果、**需人工同步清單**（DGX 實際 .env 的鍵、Supabase 需重建的表、若 Task 1 選了 stash 則提醒 `git stash pop` 恢復）、建議下一步（通知整合負責人、發 PR——依規範等使用者指示才 push）。

---

## Self-Review 紀錄

- 規格覆蓋：設計文件的五面向盤點（Task 2）、決策表（Task 3–4）、五批次執行順序與逐批測試（Task 5–9）、AGENTS.md 規範與文件同步（Task 10）、不 push／人工同步清單（Task 11）皆有對應任務。
- 佔位符檢查：改名的具體「舊名 → 新名」對照本質上依賴 Task 4 的核可結果，屬計畫的資料輸入而非佔位符；每個批次的操作程序、驗證指令與預期輸出均已具體給出。
- 一致性：各批次的 grep 排除規則（`grep -v "docs/superpowers/specs/"`）、測試基準（308 passed, 12 skipped，Task 1 若有提交則以新基準為準）前後一致。
