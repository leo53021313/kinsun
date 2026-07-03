# 取得目前時間工具 ＋ 天氣先問地點 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `get_current_time` 工具讓金孫能回答台灣時間，並讓天氣工具在不知地點時「先問」而非自行假設。

**Architecture:** 沿用既有工具工廠模式（`build_*_handler(依賴注入)` → `ToolSpec` + handler，於 `app.py` 註冊）。時間工具為無狀態、無參數工具；天氣「先問」只改工具描述與系統提示，不動 DB 與 dispatch 契約。

**Tech Stack:** Python 3.12、stdlib `datetime`、pytest；Gemini function calling（`parameters_json_schema`）。

## Global Constraints

- 一律台灣繁體中文（程式碼註解、commit 訊息、字串輸出）。
- OS-agnostic：時間一律走注入的 `now`/`tz`，不寫死。
- 工具工廠模式：依賴以參數注入，利於測試（比照 `build_weather_handler`）。
- 測試檔命名 `test_<套件>_<檔>.py`。
- commit 前綴：feat / fix / docs / refactor / test / chore。
- 不自動 push；只在 Leo 分支工作。

---

### Task 1：`get_current_time` 工具

**Files:**
- Create: `src/kinsun/tools/clock.py`
- Test: `tests/test_tools_clock.py`

**Interfaces:**
- Produces:
  - `CURRENT_TIME_SPEC: ToolSpec`（`name="get_current_time"`，`parameters={"type":"object","properties":{}}`）
  - `build_current_time_handler(now: Callable[[], datetime]) -> Callable[[dict], str]`

- [ ] **Step 1: 寫失敗測試** `tests/test_tools_clock.py`

```python
from datetime import datetime, timedelta, timezone

from kinsun.tools.clock import CURRENT_TIME_SPEC, build_current_time_handler

_TZ = timezone(timedelta(hours=8))


def _fixed(dt: datetime):
    return lambda: dt


def test_current_time_spec_name():
    assert CURRENT_TIME_SPEC.name == "get_current_time"


def test_current_time_spec_no_params():
    assert CURRENT_TIME_SPEC.parameters == {"type": "object", "properties": {}}


def test_handler_formats_afternoon():
    out = build_current_time_handler(_fixed(datetime(2026, 7, 3, 14, 30, tzinfo=_TZ)))({})
    assert "2026年7月3日" in out
    assert "星期五" in out  # 2026-07-03 為星期五
    assert "下午2點30分" in out


def test_handler_noon_on_the_hour():
    out = build_current_time_handler(_fixed(datetime(2026, 7, 3, 12, 0, tzinfo=_TZ)))({})
    assert "中午12點整" in out


def test_handler_morning_single_digit_minute():
    out = build_current_time_handler(_fixed(datetime(2026, 7, 3, 9, 5, tzinfo=_TZ)))({})
    assert "上午9點5分" in out


def test_handler_midnight_is_before_dawn():
    out = build_current_time_handler(_fixed(datetime(2026, 7, 3, 0, 15, tzinfo=_TZ)))({})
    assert "凌晨12點15分" in out
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_tools_clock.py -v`
Expected: FAIL（`ModuleNotFoundError: kinsun.tools.clock`）

- [ ] **Step 3: 寫最小實作** `src/kinsun/tools/clock.py`

```python
"""取得目前時間工具：回台灣時間的白話字串。now 可注入以利測試。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.llm import ToolSpec

CURRENT_TIME_SPEC = ToolSpec(
    name="get_current_time",
    description=(
        "取得現在的日期、星期與時間（台灣時間）。"
        "當長輩問現在幾點、今天幾號、今天星期幾時使用。"
    ),
    parameters={"type": "object", "properties": {}},
)

_WEEKDAYS = "一二三四五六日"


def _period_and_hour12(hour: int) -> tuple[str, int]:
    if hour < 5:
        period = "凌晨"
    elif hour < 12:
        period = "上午"
    elif hour == 12:
        period = "中午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    h12 = hour % 12 or 12
    return period, h12


def build_current_time_handler(now: Callable[[], datetime]) -> Callable[[dict], str]:
    def handler(_args: dict) -> str:
        current = now()
        weekday = _WEEKDAYS[current.weekday()]
        period, h12 = _period_and_hour12(current.hour)
        minute = f"{current.minute}分" if current.minute else "整"
        return (
            f"現在是 {current.year}年{current.month}月{current.day}日 "
            f"星期{weekday}，{period}{h12}點{minute}。"
        )

    return handler
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest tests/test_tools_clock.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add src/kinsun/tools/clock.py tests/test_tools_clock.py
git commit -m "feat: 新增取得目前時間工具（get_current_time，台灣時間白話字串）"
```

---

### Task 2：於 app.py 註冊時間工具

**Files:**
- Modify: `src/kinsun/app.py`（緊接現有 `registry.register(WEATHER_SPEC, ...)`）

**Interfaces:**
- Consumes: `CURRENT_TIME_SPEC`、`build_current_time_handler`（Task 1）；`tz`（app.py 既有時區變數）。

- [ ] **Step 1: 加匯入**

於 app.py 的工具匯入區（`from kinsun.tools.weather import ...` 附近）新增：

```python
from kinsun.tools.clock import CURRENT_TIME_SPEC, build_current_time_handler
```

- [ ] **Step 2: 註冊工具**

在 `registry.register(WEATHER_SPEC, build_weather_handler())` 之後新增一行：

```python
    registry.register(CURRENT_TIME_SPEC, build_current_time_handler(lambda: datetime.now(tz)))
```

- [ ] **Step 3: 驗證匯入與語法**

Run: `uv run python -c "import kinsun.app"`
Expected: 無錯誤輸出（若因缺環境變數而在 import 期報錯，改跑 `uv run ruff check src/kinsun/app.py` 確認語法/匯入正確）

- [ ] **Step 4: Commit**

```bash
git add src/kinsun/app.py
git commit -m "feat: 於 app 註冊 get_current_time 工具"
```

---

### Task 3：天氣「先問地點」（工具描述 ＋ 系統提示）

**Files:**
- Modify: `src/kinsun/tools/weather.py`（`WEATHER_SPEC.description`）
- Modify: `src/kinsun/agent.py`（`SYSTEM_PROMPT`）

**Interfaces:**
- 不改任何函式簽章；既有 `tests/test_tools_weather.py` 應持續通過。

- [ ] **Step 1: 收緊 `WEATHER_SPEC.description`**

將 `src/kinsun/tools/weather.py` 的：

```python
    description="查詢指定地點今天的天氣（概況與氣溫）。",
```

改為：

```python
    description=(
        "查詢指定地點今天的天氣（概況與氣溫）。"
        "只有在你已確認長輩要查哪個城市時才呼叫；"
        "若不知道地點，先開口問長輩人在哪個城市，不要自行假設台北。"
    ),
```

- [ ] **Step 2: 於 `SYSTEM_PROMPT` 加一句**

在 `src/kinsun/agent.py` 的 `SYSTEM_PROMPT` 內、健康衛教規則之後，加入一句（併入既有字串串接）：

```python
    "查天氣前若不知道長輩人在哪個城市，先親口問清楚，不要自己猜地點。"
```

- [ ] **Step 3: 執行既有測試確認未回歸**

Run: `uv run pytest tests/test_tools_weather.py tests/test_tools_registry.py -v`
Expected: PASS（全數通過，行為不變）

- [ ] **Step 4: Commit**

```bash
git add src/kinsun/tools/weather.py src/kinsun/agent.py
git commit -m "feat: 天氣工具先問地點——收緊工具描述與系統提示，不自行假設台北"
```

---

### Task 4：整體驗證

- [ ] **Step 1: 跑完整測試**

Run: `uv run pytest tests/test_tools_clock.py tests/test_tools_weather.py tests/test_tools_registry.py -v`
Expected: 全數 PASS

- [ ] **Step 2: 靜態檢查**

Run: `uv run ruff check src/kinsun/tools/clock.py src/kinsun/app.py src/kinsun/tools/weather.py src/kinsun/agent.py`
Expected: 無錯誤

- [ ] **Step 3（風險確認）: 無參數工具實跑**

若本機具備 `GEMINI_API_KEY`，實跑一次含 `get_current_time` 的工具迴圈，確認空 `properties` schema 不會觸發 Gemini 400。
若無金鑰無法實跑，於摘要中明確標註「未實跑、僅靜態驗證」。

## 自我檢查（Self-Review）

- Spec 覆蓋：任務 1（時間工具）→ Task 1–2；任務 2（天氣先問）→ Task 3。皆有對應。
- Placeholder：無 TBD／TODO；所有程式碼與指令均為實體內容。
- 型別一致：`CURRENT_TIME_SPEC`、`build_current_time_handler` 於 Task 1 定義、Task 2 消費，名稱一致；`parameters` 空 schema 在 spec、Task 1、Task 4 三處一致。
