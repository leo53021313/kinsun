# 長期記憶讀取時「新覆舊」矛盾消解 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓照護 agent 在長期記憶含互斥事實時依「最新自述」回應，方法是在 `Mem0LongTermStore` 讀取格式化階段依 `created_at` 由新到舊排序、標日期，並在前言加「矛盾時以較新為準」規則。

**Architecture:** 消解只發生在單一 seam —— `src/kinsun/memory/longterm/store.py` 的 `_format_memories_for_prompt`（模組函式）與 `_PREFIX`（模組常數）。Mem0 寫入維持 append-only 不動、不刪事實、無額外 LLM 呼叫或 DB 查詢。

**Tech Stack:** Python 3.12、pytest、uv、mem0 2.0.10（後端；本計畫不呼叫其新 API，僅消費既有 search 回傳的 `created_at`）。

## Global Constraints

- 語言：所有程式碼註解、commit 訊息一律台灣繁體中文、全形標點（AGENTS.md）。
- 僅改 `src/kinsun/memory/longterm/store.py` 與 `tests/test_longterm_store.py`；不動 mem0 設定、DB／schema、環境變數、依賴套件。
- 不改 Mem0 寫入路徑、不刪除/覆蓋任何長期記憶事實。
- 不新增對話熱路徑上的 LLM 呼叫或 DB 查詢。
- 測試檔命名沿用現有 `tests/test_longterm_store.py`；沿用其中既有的 `_FakeMem0` / `_ByQueryMem0` 假件風格。
- 不 push；在個人分支 Leo 上工作（AGENTS.md／CONTRIBUTING.md）。
- 括號註記四種組合皆須正確：兩者皆有 `（標籤·YYYY-MM-DD）`、僅 provenance `（標籤）`、僅日期 `（YYYY-MM-DD）`、皆無則無括號（不留空括號 `（）`）。

---

### Task 1: 在 `_format_memories_for_prompt` 實作 recency 排序、日期標註與前言規則

**Files:**
- Modify: `src/kinsun/memory/longterm/store.py`（`_PREFIX` 常數、`_format_memories_for_prompt` 函式；新增 `_created_at`、`_annotation` 兩個模組輔助函式）
- Test: `tests/test_longterm_store.py`（新增 4 個測試）

**Interfaces:**
- Consumes：mem0 2.0.10 `search` 回傳的 item dict，欄位可能含頂層 `created_at`（ISO-8601 字串）、`memory`／`text`、以及 `metadata.provenance`。
- Produces：
  - `_created_at(item: dict) -> str`：回傳 item 的 `created_at`（ISO 字串），缺值或非字串回 `""`。
  - `_annotation(item: dict) -> str`：回傳括號註記字串（provenance 標籤與日期動態組成），皆無則 `""`。
  - `_format_memories_for_prompt(result: dict) -> str`：簽章不變；輸出改為由新到舊排序、每行帶註記、前言含新覆舊規則。

- [ ] **Step 1：寫失敗測試（排序、日期、前言、缺值防呆）**

在 `tests/test_longterm_store.py` 末端新增：

```python
def test_format_orders_newest_first():
    result = {
        "results": [
            {"memory": "喜歡壽司", "created_at": "2026-07-03T19:01:08+00:00", "metadata": {}},
            {"memory": "喜歡麥當勞", "created_at": "2026-07-04T02:30:41+00:00", "metadata": {}},
        ]
    }
    out = _format_memories_for_prompt(result)
    assert out.index("喜歡麥當勞") < out.index("喜歡壽司")  # 新的排在前


def test_format_annotates_date_and_provenance():
    result = {
        "results": [
            {
                "memory": "喜歡麥當勞",
                "created_at": "2026-07-04T02:30:41+00:00",
                "metadata": {"provenance": "self_claimed"},
            }
        ]
    }
    out = _format_memories_for_prompt(result)
    assert "2026-07-04" in out
    assert "長者自述" in out
    assert "（）" not in out


def test_format_prefix_has_recency_rule():
    result = {
        "results": [
            {"memory": "喜歡麥當勞", "created_at": "2026-07-04T02:30:41+00:00", "metadata": {}}
        ]
    }
    out = _format_memories_for_prompt(result)
    assert "以較新的記錄為準" in out


def test_format_missing_created_at_sorts_last_no_crash():
    result = {
        "results": [
            {"memory": "沒日期的事實", "metadata": {"provenance": "self_claimed"}},
            {"memory": "喜歡麥當勞", "created_at": "2026-07-04T02:30:41+00:00", "metadata": {}},
        ]
    }
    out = _format_memories_for_prompt(result)
    assert "沒日期的事實" in out
    assert "喜歡麥當勞" in out
    assert out.index("喜歡麥當勞") < out.index("沒日期的事實")  # 有日期者在前
    assert "（）" not in out  # 無日期無 provenance 不留空括號
```

- [ ] **Step 2：跑新測試，確認失敗**

Run: `cd /home/leo29/kinsun && PYTHONPATH=src uv run pytest tests/test_longterm_store.py -k "orders_newest_first or annotates_date or prefix_has_recency or missing_created_at" -v`
Expected: FAIL（`test_format_orders_newest_first` 斷言順序失敗／或前言、日期斷言失敗；因目前函式未排序、未標日期、前言無新規則）。

- [ ] **Step 3：改 `_PREFIX` 常數**

將 `src/kinsun/memory/longterm/store.py` 現有：

```python
_PREFIX = "\n以下為這位長者的長期記憶（部分為長者自述、未必經確認，請勿當成醫療診斷）：\n"
```

改為：

```python
_PREFIX = (
    "\n以下為這位長者的長期記憶（部分為長者自述、未必經確認，請勿當成醫療診斷）；"
    "已由新到舊排列並附記錄日期。若前後有矛盾，請以較新的記錄為準，"
    "並顧及長者感受、不主動糾正；日期僅供你判斷新舊，回覆時不必提及：\n"
)
```

- [ ] **Step 4：新增輔助函式並改寫 `_format_memories_for_prompt`**

將 `src/kinsun/memory/longterm/store.py` 現有的 `_format_memories_for_prompt`（整段）：

```python
def _format_memories_for_prompt(result: dict) -> str:
    items = result.get("results") or []
    if not items:
        return ""
    lines = []
    for item in items:
        text = item.get("memory") or item.get("text") or ""
        if not text:
            continue
        src = (item.get("metadata") or {}).get("provenance")
        suffix = f"（{prov.label(src)}）" if src else ""
        lines.append(f"- {text}{suffix}")
    if not lines:
        return ""
    return _PREFIX + "\n".join(lines) + "\n"
```

替換為（新增兩個輔助函式 + 加入排序與註記）：

```python
def _created_at(item: dict) -> str:
    """取出 mem0 item 的 created_at（ISO 字串）；缺值或非字串回空字串。"""
    value = item.get("created_at") or (item.get("metadata") or {}).get("created_at")
    return value if isinstance(value, str) else ""


def _annotation(item: dict) -> str:
    """組 provenance 標籤與日期的括號註記；兩段動態組成，皆無則回空字串。"""
    parts = []
    src = (item.get("metadata") or {}).get("provenance")
    if src:
        parts.append(prov.label(src))
    created_at = _created_at(item)
    if created_at:
        parts.append(created_at[:10])  # ISO-8601 前 10 碼即 YYYY-MM-DD
    return f"（{'·'.join(parts)}）" if parts else ""


def _format_memories_for_prompt(result: dict) -> str:
    items = result.get("results") or []
    if not items:
        return ""
    # 由新到舊：created_at 遞減；缺 created_at（回空字串）者排最後。
    ordered = sorted(items, key=_created_at, reverse=True)
    lines = []
    for item in ordered:
        text = item.get("memory") or item.get("text") or ""
        if not text:
            continue
        lines.append(f"- {text}{_annotation(item)}")
    if not lines:
        return ""
    return _PREFIX + "\n".join(lines) + "\n"
```

- [ ] **Step 5：跑新測試，確認通過**

Run: `cd /home/leo29/kinsun && PYTHONPATH=src uv run pytest tests/test_longterm_store.py -k "orders_newest_first or annotates_date or prefix_has_recency or missing_created_at" -v`
Expected: PASS（4 個新測試全綠）。

- [ ] **Step 6：跑整個 `test_longterm_store.py`，確認既有測試未回歸**

Run: `cd /home/leo29/kinsun && PYTHONPATH=src uv run pytest tests/test_longterm_store.py -v`
Expected: PASS（含既有 `test_format_lists_memories_with_provenance`、`test_search_returns_formatted_string` 等；它們斷言子字串 `長者自述`／`喜歡下棋`／`有高血壓`，新格式仍含這些）。

- [ ] **Step 7：Commit**

```bash
cd /home/leo29/kinsun
git add src/kinsun/memory/longterm/store.py tests/test_longterm_store.py
git commit -m "$(cat <<'EOF'
feat: 長期記憶讀取時依 created_at 新覆舊消解矛盾

Mem0LongTermStore 格式化時由新到舊排序、每筆標記錄日期，前言加
「矛盾時以較新為準、不主動糾正」規則。append-only 不刪舊事實、
零額外 LLM 呼叫。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 全套測試回歸 + 人工驗證真實帳號 recall

**Files:**
- 無程式碼變更（驗證任務）。

**Interfaces:**
- Consumes：Task 1 完成後的 `Mem0LongTermStore`。

- [ ] **Step 1：跑全套單元測試**

Run: `cd /home/leo29/kinsun && PYTHONPATH=src uv run pytest -q`
Expected: PASS（全綠；本改動僅動格式化字串，不影響其他套件。若有連 Postgres 的整合測試以 `KINSUN_IT` 控制、未啟用則略過屬正常）。

- [ ] **Step 2：人工驗證真實資料的 recall 輸出**

Run（唯讀，只呼叫 search，不寫入）：

```bash
cd /home/leo29/kinsun && PYTHONPATH=src uv run python - <<'PY'
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from kinsun.config import load_dotenv, load_settings
from kinsun.db import Database
from kinsun.memory.longterm.mem0_factory import build_mem0_memory
from kinsun.memory.longterm.store import Mem0LongTermStore

load_dotenv()
s = load_settings(os.environ)
store = Mem0LongTermStore(build_mem0_memory(s), top_k=s.longterm_top_k)
out = store.search("Ud1c7fcbda997f9247cfbf6ad911a60a6", "我喜歡吃什麼")
print(out)
PY
```

Expected: 記憶區塊前言含「以較新的記錄為準」；「麥當勞」那筆（2026-07-04）排在「壽司」那筆（2026-07-03）之前，且各行帶 `（長者自述·YYYY-MM-DD）` 註記。

- [ ] **Step 3：人工判讀並記錄結果**

確認上一步輸出符合預期即為通過；若「壽司」仍排在「麥當勞」前或缺日期，回 Task 1 檢查排序鍵與 `created_at` 取值。無需 commit（本任務不改碼）。

---

## Self-Review

**1. Spec coverage：**
- 讀取時消解、append-only → Task 1（只改格式化、不動寫入）✓
- 由新到舊排序 → Task 1 Step 4（`sorted(..., key=_created_at, reverse=True)`）✓
- 每筆標日期、四種括號組合 → Task 1 Step 4（`_annotation`）＋ Step 1 測試涵蓋 ✓
- 前言新覆舊規則 → Task 1 Step 3 ＋ `test_format_prefix_has_recency_rule` ✓
- 缺 created_at 排最後不崩 → `test_format_missing_created_at_sorts_last_no_crash` ✓
- 不丟非矛盾舊事實（不過濾）→ Task 1 未加任何 filter，僅重排 ✓
- 零額外 LLM／DB → Task 1 純字串處理 ✓
- 既有測試不回歸 → Task 1 Step 6 ✓
- 人工驗證壽司/麥當勞 → Task 2 Step 2 ✓

**2. Placeholder scan：** 無 TBD／TODO；每個 code step 均含完整程式碼與確切指令。✓

**3. Type consistency：** `_created_at`／`_annotation`／`_format_memories_for_prompt` 簽章在 Task 1 定義並於同函式內使用，命名一致；`prov.label` 沿用 store.py 既有匯入別名（`from kinsun.memory.longterm import provenance as prov`）。✓
