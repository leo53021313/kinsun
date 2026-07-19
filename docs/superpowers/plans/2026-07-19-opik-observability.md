# Opik 工程觀測整合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把自架 Opik 接成 kinsun 的「工程/LLM 深度視角」觀測層（trace + 巢狀 span + LLM 自動捕捉 + 離線評測），與現有自建 `observability/` 業務後台並存、互不干擾。

**Architecture:** 新增單一 `kinsun.tracing` 模組作為唯一 `import opik` 之處（比照 `rag/vector_store.py` 外部 adapter 定位，免三件套）；其餘程式只依賴 `tracing` 的薄封裝。以 `OPIK_ENABLED` 旗標全域開關——關閉時所有裝飾器/包裝退化為 no-op，零行為改變。用 `track_genai` 包 `GeminiClient` 的底層 client 取得 LLM 自動捕捉，用 `@tracing.track` 為 pipeline 各階段長出巢狀 span，並把 kinsun 現成的 `trace_id` 以 metadata 掛上 Opik trace 做關聯。

**Tech Stack:** Python ≥3.10、pytest、uv、`opik` SDK 2.1.x（純 Python wheel，arm64 相容）、Google GenAI SDK（`google-genai`）、自架 Opik 於 DGX（`/home/leo29/opik`，UI `http://localhost:5273`、API `http://localhost:5273/api`）。

## Global Constraints

- 語言一律台灣繁體中文（程式碼註解、commit、文件）；用語對照見 `AGENTS.md`。
- 命名：`Settings` 欄位名＝環境變數鍵小寫，一一對應；新子系統前綴 `OPIK_`；每個讀取的鍵都要列進 `.env.example` 附預設值＋一行中文註解。
- OS-agnostic、ARM64 相容；新增依賴須有 `linux/aarch64` wheel（`opik` 為 `py3-none-any.whl`，已確認）。
- 觀測失敗絕不中斷對話：所有 Opik 呼叫比照現有 `safe_record` 精神，以 `try/except` 吞掉並記 warning。
- 最小改動：只碰完成需求所必須的檔案；不順手重構、不改格式、不大量重新命名。
- 預設關閉（`OPIK_ENABLED=false`）＝完全 no-op；開啟才有任何 Opik 行為。
- 測試檔名 `test_<套件>_<檔>.py`；離線單元測試不得連任何外部服務（含 Opik）。
- docs/dev 同步鐵律：本計畫完成時同批更新 `docs/dev/` 與 `.env.example`、`pyproject.toml`。
- 不自動 push；只在 `feat/opik-observability` 分支工作；一個 commit 做一件事。

---

## 前置作業（Pre-flight，開工前一次）

- [ ] **確認分支**：目前在 `Leo` 且有未提交的 docs 變更。先處理乾淨再開新分支。

Run:
```bash
git -C /home/leo29/kinsun status --short
git -C /home/leo29/kinsun stash push -u -m "wip-docs-before-opik" 2>/dev/null || true
git -C /home/leo29/kinsun checkout -b feat/opik-observability
git -C /home/leo29/kinsun branch --show-current
```
Expected: 印出 `feat/opik-observability`。

- [ ] **確認 Opik 服務在跑**（本計畫的整合目標）。

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5273/api/v1/private/projects
```
Expected: `200`（若非 200，先 `cd /home/leo29/opik && ./opik.sh`）。

---

## File Structure

新增：
- `src/kinsun/tracing/__init__.py` — 對外公開 API（re-export）。
- `src/kinsun/tracing/client.py` — 設定/開關/no-op 守門；唯一決定 `is_enabled()` 的地方。
- `src/kinsun/tracing/decorators.py` — `track` 裝飾器（延後到呼叫時判斷開關）＋ `tag_current_trace`。
- `src/kinsun/tracing/genai.py` — `wrap_genai`：包 google-genai client。
- `evals/README.md`、`evals/datasets/careline_smoke.py`、`evals/experiments/hallucination.py` — 離線評測。
- 測試：`tests/test_tracing_client.py`、`tests/test_tracing_decorators.py`、`tests/test_tracing_genai.py`。

修改：
- `src/kinsun/config.py` — `Settings` 加 4 個 `opik_*` 欄位 + `load_settings` 讀取。
- `src/kinsun/llm.py` — `GeminiClient` / `build_gemini_for` 加 `client_wrapper` 參數。
- `src/kinsun/composition.py` — `build_externals` 呼叫 `tracing.configure` 並以 `wrap_genai` 包 Gemini。
- `src/kinsun/pipeline.py` — `process` / `process_text` 為 trace root，四個階段方法加 span。
- `src/kinsun/tools/registry.py` — `dispatch` 加 tool span（深度）。
- `src/kinsun/rag/retriever.py` — 檢索方法加 span（深度）。
- `.env.example`、`pyproject.toml`、`docs/dev/`。

依賴方向（單向、可插拔）：`llm / pipeline / tools / rag / evals → kinsun.tracing → opik SDK`。`observability/` 不依賴 `tracing/`。

---

## Phase 1：地基（設定 + tracing 模組，全離線可測，不碰主流程）

### Task 1：新增 OPIK_ 設定與依賴

**Files:**
- Modify: `src/kinsun/config.py:41-116`（`Settings` 欄位）、`src/kinsun/config.py:247-352`（`load_settings` return）
- Modify: `.env.example`（新增 OPIK_ 區塊）
- Modify: `pyproject.toml`（新增 `opik` 依賴）
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.opik_enabled: bool`、`Settings.opik_url_override: str`、`Settings.opik_workspace: str`、`Settings.opik_project_name: str`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_config.py` 末尾新增：
```python
def test_opik_settings_default_disabled():
    from kinsun.config import load_settings

    env = {
        "LINE_CHANNEL_SECRET": "s",
        "LINE_CHANNEL_ACCESS_TOKEN": "t",
        "GEMINI_API_KEY": "k",
        "DATABASE_URL": "postgresql://x",
    }
    settings = load_settings(env)
    assert settings.opik_enabled is False
    assert settings.opik_url_override == "http://localhost:5273/api"
    assert settings.opik_workspace == "default"
    assert settings.opik_project_name == "kinsun"


def test_opik_enabled_parses_truthy():
    from kinsun.config import load_settings

    env = {
        "LINE_CHANNEL_SECRET": "s",
        "LINE_CHANNEL_ACCESS_TOKEN": "t",
        "GEMINI_API_KEY": "k",
        "DATABASE_URL": "postgresql://x",
        "OPIK_ENABLED": "true",
        "OPIK_PROJECT_NAME": "kinsun-dev",
    }
    settings = load_settings(env)
    assert settings.opik_enabled is True
    assert settings.opik_project_name == "kinsun-dev"
```

- [ ] **Step 2: 執行確認失敗**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_config.py::test_opik_settings_default_disabled -q`
Expected: FAIL（`AttributeError: ... 'Settings' object has no attribute 'opik_enabled'`）。

- [ ] **Step 3: 加欄位**

在 `src/kinsun/config.py` 的 `Settings` dataclass 末欄（`proactive_greeting_lag_tolerance_minutes: int` 之後）新增：
```python
    opik_enabled: bool
    opik_url_override: str
    opik_workspace: str
    opik_project_name: str
```

- [ ] **Step 4: 加讀取**

在 `src/kinsun/config.py` `load_settings` 的 `return Settings(` 內、最後一個欄位（`reflection_max_turns=...`）之後新增：
```python
        # 工程觀測 Opik（OPIK_ 前綴）：預設關閉＝全模組 no-op；開啟才送 trace。
        opik_enabled=_parse_bool(env.get("OPIK_ENABLED", "false")),
        opik_url_override=env.get("OPIK_URL_OVERRIDE", "http://localhost:5273/api"),
        opik_workspace=env.get("OPIK_WORKSPACE", "default"),
        opik_project_name=env.get("OPIK_PROJECT_NAME", "kinsun"),
```

- [ ] **Step 5: 執行確認通過**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_config.py -q`
Expected: PASS（含既有測試）。

- [ ] **Step 6: 補 .env.example**

在 `.env.example` 末尾新增：
```bash
# ────── 工程觀測 Opik（OPIK_ 前綴；工程/LLM 深度視角，與自建 observability 後台並存） ──────
# 總開關：false＝全模組 no-op（預設，零行為改變）；true 才送 trace 到自架 Opik。
OPIK_ENABLED=false
# 自架 Opik 後端位址（前端 nginx 反代 API）；DGX 本機自架見 /home/leo29/opik。
OPIK_URL_OVERRIDE=http://localhost:5273/api
# 自架工作區（單機自架預設 default）。
OPIK_WORKSPACE=default
# 專案名（Opik UI 內的分組標籤）。
OPIK_PROJECT_NAME=kinsun
```

- [ ] **Step 7: 加依賴**

Run:
```bash
cd /home/leo29/kinsun && uv add 'opik>=2.1,<3'
```
Expected: `pyproject.toml` 出現 `opik>=2.1,<3`，`uv.lock` 更新，安裝成功（arm64 純 Python wheel）。

- [ ] **Step 8: Commit**

```bash
git add src/kinsun/config.py tests/test_config.py .env.example pyproject.toml uv.lock
git commit -m "feat(tracing): add OPIK_ settings and opik dependency"
```

---

### Task 2：tracing/client.py — 設定與開關守門

**Files:**
- Create: `src/kinsun/tracing/__init__.py`
- Create: `src/kinsun/tracing/client.py`
- Test: `tests/test_tracing_client.py`

**Interfaces:**
- Produces:
  - `configure(settings) -> None`：讀 `opik_*` 設定；停用或缺 `opik` 套件時 `is_enabled()` 恆 False。
  - `is_enabled() -> bool`
  - `reset_for_test() -> None`：測試用，清回未設定狀態。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_tracing_client.py`:
```python
from dataclasses import dataclass

from kinsun.tracing import client as tracing_client


@dataclass
class _S:
    opik_enabled: bool
    opik_url_override: str = "http://localhost:5273/api"
    opik_workspace: str = "default"
    opik_project_name: str = "kinsun"


def test_disabled_settings_keep_tracing_off():
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=False))
    assert tracing_client.is_enabled() is False


def test_before_configure_is_disabled():
    tracing_client.reset_for_test()
    assert tracing_client.is_enabled() is False


def test_enabled_settings_export_env_and_turn_on(monkeypatch):
    monkeypatch.delenv("OPIK_URL_OVERRIDE", raising=False)
    monkeypatch.delenv("OPIK_WORKSPACE", raising=False)
    monkeypatch.delenv("OPIK_PROJECT_NAME", raising=False)
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=True))
    import os

    assert tracing_client.is_enabled() is True
    assert os.environ["OPIK_URL_OVERRIDE"] == "http://localhost:5273/api"
    assert os.environ["OPIK_WORKSPACE"] == "default"
    assert os.environ["OPIK_PROJECT_NAME"] == "kinsun"
```

- [ ] **Step 2: 執行確認失敗**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_tracing_client.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'kinsun.tracing'`）。

- [ ] **Step 3: 建 __init__.py**

Create `src/kinsun/tracing/__init__.py`:
```python
"""工程觀測（Opik）整合：唯一 import opik 之處，其餘程式只依賴本套件的薄封裝。

比照 rag/vector_store.py 的外部服務 adapter 定位（免三件套）。以 OPIK_ENABLED
全域開關——關閉時所有裝飾器/包裝退化為 no-op，對主流程零影響。
"""

from __future__ import annotations

from kinsun.tracing.client import configure, is_enabled

__all__ = ["configure", "is_enabled"]
```

- [ ] **Step 4: 建 client.py**

Create `src/kinsun/tracing/client.py`:
```python
"""Opik 設定與全域開關；唯一決定 is_enabled() 的地方。"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("kinsun.tracing")

_ENABLED = False


def configure(settings) -> None:
    """依設定啟用/停用 Opik。停用或未安裝 opik 套件時，is_enabled() 恆 False。

    只設環境變數與旗標，不建立連線（連線由 opik SDK 首次送 trace 時自建）。
    以 setdefault 讓真實環境變數優先（與 config.load_dotenv 一致）。
    """
    global _ENABLED
    if not settings.opik_enabled:
        _ENABLED = False
        return
    try:
        import opik  # noqa: F401  只確認可匯入
    except ImportError:
        logger.warning("OPIK_ENABLED=true 但未安裝 opik 套件；工程觀測停用。")
        _ENABLED = False
        return
    os.environ.setdefault("OPIK_URL_OVERRIDE", settings.opik_url_override)
    os.environ.setdefault("OPIK_WORKSPACE", settings.opik_workspace)
    os.environ.setdefault("OPIK_PROJECT_NAME", settings.opik_project_name)
    _ENABLED = True
    logger.info("Opik 工程觀測已啟用：%s", settings.opik_url_override)


def is_enabled() -> bool:
    return _ENABLED


def reset_for_test() -> None:
    """測試用：清回未設定狀態。"""
    global _ENABLED
    _ENABLED = False
```

- [ ] **Step 5: 執行確認通過**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_tracing_client.py -q`
Expected: PASS（3 passed）。

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/tracing/__init__.py src/kinsun/tracing/client.py tests/test_tracing_client.py
git commit -m "feat(tracing): add Opik enable/config gate with no-op fallback"
```

---

### Task 3：tracing/decorators.py — track 裝飾器與 trace 標記

**Files:**
- Create: `src/kinsun/tracing/decorators.py`
- Modify: `src/kinsun/tracing/__init__.py`
- Test: `tests/test_tracing_decorators.py`

**Interfaces:**
- Consumes: `kinsun.tracing.client.is_enabled`
- Produces:
  - `track(name=None, type="general", capture_input=True, capture_output=True)` → 裝飾器；**呼叫時**才判斷開關（因裝飾器在 import 期套用，早於 configure）。停用＝原函式；啟用＝lazy 包成 `opik.track`。
  - `tag_current_trace(*, trace_id, channel="", elder_id="") -> None`：把 kinsun trace_id 以 metadata/tags 掛到當前 Opik trace；停用或失敗皆 no-op。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_tracing_decorators.py`:
```python
from kinsun import tracing
from kinsun.tracing import client as tracing_client


def test_track_is_identity_when_disabled():
    tracing_client.reset_for_test()  # 停用
    calls = []

    @tracing.track(name="x")
    def f(a):
        calls.append(a)
        return a * 2

    assert f(3) == 6
    assert calls == [3]


def test_track_defers_enable_check_to_call_time(monkeypatch):
    # 裝飾時停用、呼叫時啟用：仍應正常執行原邏輯（此處驗證不炸、回傳正確）。
    tracing_client.reset_for_test()

    @tracing.track(name="y")
    def g(a):
        return a + 1

    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(tracing_client, "is_enabled", lambda: True)
    # opik.track 存在且可用；即使包裝，回傳值不變。
    assert g(41) == 42


def test_tag_current_trace_noop_when_disabled():
    tracing_client.reset_for_test()
    # 停用時純 no-op、不得拋例外。
    assert tracing.tag_current_trace(trace_id="abc", channel="line") is None
```

- [ ] **Step 2: 執行確認失敗**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_tracing_decorators.py -q`
Expected: FAIL（`AttributeError: module 'kinsun.tracing' has no attribute 'track'`）。

- [ ] **Step 3: 建 decorators.py**

Create `src/kinsun/tracing/decorators.py`:
```python
"""track 裝飾器與 trace 標記；停用時全部 no-op。"""

from __future__ import annotations

import functools
import logging

from kinsun.tracing.client import is_enabled

logger = logging.getLogger("kinsun.tracing")


def track(name=None, type="general", capture_input=True, capture_output=True):
    """為函式加 Opik span。開關判斷延後到呼叫時（裝飾器在 import 期套用，早於 configure）。

    停用＝直接跑原函式；啟用＝首次呼叫時才 lazy 包成 opik.track 並快取。
    """

    def decorator(func):
        opik_wrapped = None

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal opik_wrapped
            if not is_enabled():
                return func(*args, **kwargs)
            if opik_wrapped is None:
                from opik import track as opik_track

                opik_wrapped = opik_track(
                    name=name,
                    type=type,
                    capture_input=capture_input,
                    capture_output=capture_output,
                )(func)
            return opik_wrapped(*args, **kwargs)

        return wrapper

    return decorator


def tag_current_trace(*, trace_id, channel="", elder_id="") -> None:
    """把 kinsun 的 trace_id 掛到當前 Opik trace（metadata + tags），供 UI 關聯與搜尋。

    觀測失敗不可中斷對話：任何例外都吞掉並記 warning。停用時 no-op。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        opik_context.update_current_trace(
            metadata={"kinsun_trace_id": trace_id, "elder_id": elder_id},
            tags=[t for t in (channel,) if t],
        )
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik trace 標記失敗 trace=%s", trace_id)
```

- [ ] **Step 4: 匯出**

在 `src/kinsun/tracing/__init__.py` 更新：
```python
from kinsun.tracing.client import configure, is_enabled
from kinsun.tracing.decorators import tag_current_trace, track

__all__ = ["configure", "is_enabled", "tag_current_trace", "track"]
```

- [ ] **Step 5: 執行確認通過**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_tracing_decorators.py -q`
Expected: PASS（3 passed）。

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/tracing/decorators.py src/kinsun/tracing/__init__.py tests/test_tracing_decorators.py
git commit -m "feat(tracing): add call-time-gated track decorator and trace tagging"
```

---

### Task 4：tracing/genai.py — 包 google-genai client

**Files:**
- Create: `src/kinsun/tracing/genai.py`
- Modify: `src/kinsun/tracing/__init__.py`
- Test: `tests/test_tracing_genai.py`

**Interfaces:**
- Consumes: `kinsun.tracing.client.is_enabled`
- Produces: `wrap_genai(client)` → 停用時原樣回傳；啟用時回傳 `opik.integrations.genai.track_genai(client)`。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_tracing_genai.py`:
```python
from kinsun import tracing
from kinsun.tracing import client as tracing_client


def test_wrap_genai_is_identity_when_disabled():
    tracing_client.reset_for_test()
    sentinel = object()
    assert tracing.wrap_genai(sentinel) is sentinel
```

- [ ] **Step 2: 執行確認失敗**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_tracing_genai.py -q`
Expected: FAIL（`AttributeError: module 'kinsun.tracing' has no attribute 'wrap_genai'`）。

- [ ] **Step 3: 建 genai.py**

Create `src/kinsun/tracing/genai.py`:
```python
"""包 google-genai client，取得 LLM 呼叫的自動捕捉（輸入/輸出/token/模型參數）。"""

from __future__ import annotations

import logging

from kinsun.tracing.client import is_enabled

logger = logging.getLogger("kinsun.tracing")


def wrap_genai(client):
    """啟用時以 Opik 包裝 google-genai client；停用或包裝失敗則原樣回傳。"""
    if not is_enabled():
        return client
    try:
        from opik.integrations.genai import track_genai

        return track_genai(client)
    except Exception:  # noqa: BLE001 - 包裝失敗不可影響 LLM 可用性
        logger.warning("track_genai 包裝失敗；LLM 觀測略過。")
        return client
```

- [ ] **Step 4: 匯出**

在 `src/kinsun/tracing/__init__.py` 更新：
```python
from kinsun.tracing.client import configure, is_enabled
from kinsun.tracing.decorators import tag_current_trace, track
from kinsun.tracing.genai import wrap_genai

__all__ = ["configure", "is_enabled", "tag_current_trace", "track", "wrap_genai"]
```

- [ ] **Step 5: 執行確認通過**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_tracing_genai.py -q`
Expected: PASS（1 passed）。

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/tracing/genai.py src/kinsun/tracing/__init__.py tests/test_tracing_genai.py
git commit -m "feat(tracing): add wrap_genai for google-genai auto-instrumentation"
```

---

## Phase 2：接線（feature-flag 包裹，預設關閉零影響）

### Task 5：llm.py — GeminiClient 接受 client_wrapper

**Files:**
- Modify: `src/kinsun/llm.py:139-147`（`GeminiClient.__init__`）、`src/kinsun/llm.py:231-235`（`build_gemini_for`）
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces:
  - `GeminiClient(*, api_key, model, timeout, client_wrapper=None)`：`client_wrapper` 為 `Callable[[client], client]`，`None`＝不包裝。
  - `build_gemini_for(settings, model, *, client_wrapper=None) -> GeminiClient`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_llm.py` 末尾新增：
```python
def test_gemini_client_applies_client_wrapper():
    from kinsun.llm import GeminiClient

    marker = object()
    seen = {}

    def wrapper(client):
        seen["inner"] = client
        return marker

    client = GeminiClient(api_key="dummy", model="m", timeout=30.0, client_wrapper=wrapper)
    assert client._client is marker
    assert seen["inner"] is not None  # 底層 genai.Client 有被建出來並傳入


def test_gemini_client_without_wrapper_keeps_native_client():
    from kinsun.llm import GeminiClient

    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    assert client._client is not None
```

- [ ] **Step 2: 執行確認失敗**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_llm.py::test_gemini_client_applies_client_wrapper -q`
Expected: FAIL（`TypeError: __init__() got an unexpected keyword argument 'client_wrapper'`）。

- [ ] **Step 3: 改 GeminiClient.__init__**

把 `src/kinsun/llm.py` 的 `GeminiClient.__init__` 改為：
```python
class GeminiClient:
    def __init__(
        self, *, api_key: str, model: str, timeout: float, client_wrapper=None
    ) -> None:
        if not api_key:
            raise LLMError("缺少 GEMINI_API_KEY")
        from google import genai

        client = genai.Client(api_key=api_key)
        # client_wrapper 為觀測層的注入點（如 Opik track_genai）；None＝不包裝。
        # 保持 llm.py 不 import 觀測套件（依賴反轉），包裝由組裝層決定。
        self._client = client_wrapper(client) if client_wrapper is not None else client
        self._model = model
        self._timeout = timeout
```

- [ ] **Step 4: 改 build_gemini_for**

把 `src/kinsun/llm.py` 的 `build_gemini_for` 改為：
```python
def build_gemini_for(settings, model: str, *, client_wrapper=None) -> GeminiClient:
    """按用途建 Gemini client（✅ D-16 丁-5）：模型同主設定時呼叫端應直接共用主 client。"""
    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=model,
        timeout=settings.gemini_timeout_seconds,
        client_wrapper=client_wrapper,
    )
```

- [ ] **Step 5: 執行確認通過**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_llm.py -q`
Expected: PASS（含既有測試；既有測試不傳 `client_wrapper`，行為不變）。

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/llm.py tests/test_llm.py
git commit -m "feat(llm): add optional client_wrapper injection point to GeminiClient"
```

---

### Task 6：composition.py — 啟用 Opik 並包 Gemini

**Files:**
- Modify: `src/kinsun/composition.py:105-120`（`build_externals`）
- Modify: `src/kinsun/composition.py`（`build_gemini_for` 呼叫處，如有）
- Test: `tests/test_composition.py`

**Interfaces:**
- Consumes: `kinsun.tracing.configure`、`kinsun.tracing.wrap_genai`、`Settings.opik_*`
- Produces: `Externals.gemini` 於 `OPIK_ENABLED=true` 時為 track_genai 包裝後的 client；`false` 時與現況完全相同。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_composition.py` 末尾新增（純驗證接線呼叫，不連網）：
```python
def test_build_externals_configures_tracing(monkeypatch):
    import kinsun.composition as composition
    from kinsun import tracing

    configured = {}

    def fake_configure(settings):
        configured["called"] = settings.opik_enabled

    monkeypatch.setattr(tracing, "configure", fake_configure)
    monkeypatch.setattr(tracing, "wrap_genai", lambda c: c)
    # 阻斷真正的外部連線：只驗證 configure 有被呼叫。
    monkeypatch.setattr(composition, "ensure_schema", lambda url: None)

    class _FakeDB:
        @staticmethod
        def open(url, max_size):
            return object()

    monkeypatch.setattr(composition, "Database", _FakeDB)
    monkeypatch.setattr(composition, "GeminiClient", lambda **kw: object())
    monkeypatch.setattr(composition, "Mem0LongTermStore", lambda *a, **k: object())
    monkeypatch.setattr(composition, "build_mem0_memory", lambda s: object())
    monkeypatch.setattr(composition, "LineApiMessenger", lambda t: object())

    from kinsun.config import load_settings

    settings = load_settings(
        {
            "LINE_CHANNEL_SECRET": "s",
            "LINE_CHANNEL_ACCESS_TOKEN": "t",
            "GEMINI_API_KEY": "k",
            "DATABASE_URL": "postgresql://x",
            "OPIK_ENABLED": "false",
        }
    )
    composition.build_externals(settings)
    assert configured["called"] is False
```

> 備註：`tests/factories.py` 不存在，`test_composition.py` 既有測試即以 `kinsun.config.load_settings` 建 settings（見檔頭 import），此測試沿用同一路徑。

- [ ] **Step 2: 執行確認失敗**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_composition.py::test_build_externals_configures_tracing -q`
Expected: FAIL（`configured` 無 `called` 鍵，因 `build_externals` 尚未呼叫 `tracing.configure`）。

- [ ] **Step 3: 改 build_externals**

在 `src/kinsun/composition.py` 頂部 import 區新增：
```python
from kinsun import tracing
```
把 `build_externals` 改為（新增第一行 configure 與 gemini 包裝）：
```python
def build_externals(settings: Settings) -> Externals:
    """接外部相依：先建表，再開連線與各外部 client。會連線，不進單元測試。"""
    # 工程觀測開關在最前面決定（configure 只設環境變數與旗標，不連線）。
    tracing.configure(settings)
    ensure_schema(settings.database_url)
    db = Database.open(settings.database_url, max_size=settings.database_pool_max_size)
    gemini = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout_seconds,
        client_wrapper=tracing.wrap_genai,
    )
    long_term = Mem0LongTermStore(
        build_mem0_memory(settings),
        top_k=settings.longterm_top_k,
        health_top_k=settings.longterm_health_top_k,
    )
    messenger = LineApiMessenger(settings.line_channel_access_token)
    return Externals(db=db, gemini=gemini, long_term=long_term, messenger=messenger)
```

- [ ] **Step 4: 包其他 Gemini client（安全/摘要模型）**

Run（找出所有 `build_gemini_for` 呼叫處）：
```bash
grep -rn "build_gemini_for(" src/kinsun --include="*.py"
```
對每一處呼叫，補上 `client_wrapper=tracing.wrap_genai` 參數（該檔若尚未 import，加 `from kinsun import tracing`）。範例：
```python
# 之前
detector_llm = build_gemini_for(settings, settings.gemini_model_safety)
# 之後
detector_llm = build_gemini_for(
    settings, settings.gemini_model_safety, client_wrapper=tracing.wrap_genai
)
```

- [ ] **Step 5: 執行確認通過**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_composition.py tests/test_llm.py -q`
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/composition.py tests/test_composition.py
git commit -m "feat(composition): configure Opik and wrap all Gemini clients"
```

---

### Task 7：pipeline.py — 階段 span 與 trace 標記

**Files:**
- Modify: `src/kinsun/pipeline.py:1-22`（import）、`:65-104`（`process`/`process_text`）、`:230-300`（四個階段方法）
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `kinsun.tracing.track`、`kinsun.tracing.tag_current_trace`
- Produces: `process`/`process_text` 為 Opik trace root；`_transcribe`/`_assess`/`_generate`/`_synthesize` 為子 span。停用時全部 no-op，回傳與現況一致。

- [ ] **Step 1: 寫失敗測試（no-op 行為守恆）**

在 `tests/test_pipeline.py` 末尾新增：
```python
def test_pipeline_process_text_unchanged_when_tracing_disabled():
    from kinsun.tracing import client as tracing_client

    tracing_client.reset_for_test()  # 停用
    traces = FakeTraceStore()
    pipeline = _pipeline_with_traces(traces)  # 見備註
    result = pipeline.process_text(
        "阿嬤今天想吃什麼", elder_id="e1", external_id="u1", channel="line", trace_id="t1"
    )
    assert result.text  # 回覆照常產生
    # 自建觀測（業務視角）照常記錄，不受工程觀測影響。
    assert traces.llm_calls  # 至少記到一筆 llm_call
```

> 備註：`_pipeline_with_traces` 沿用檔內既有建構樣式（見 `tests/test_pipeline.py:307` 附近以 `FakeTraceStore()` 建 `VoicePipeline` 的既有測試），把 `traces=` 傳入即可；若已有等價 helper 直接重用，不要新增重複 helper（DRY）。

- [ ] **Step 2: 執行確認（此測試應直接 PASS）**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_pipeline.py -q`
Expected: PASS。此為「守恆測試」——先確立停用時行為不變的基準，Step 3 的裝飾器不得破壞它。

- [ ] **Step 3: 加 import 與裝飾器**

在 `src/kinsun/pipeline.py` import 區（`from kinsun.observability.store import ...` 附近）新增：
```python
from kinsun import tracing
```
為 `process` 加裝飾器並在函式體第一行標記 trace（`audio` 為 bytes，故 `capture_input=False`）：
```python
    @tracing.track(name="care_turn_voice", type="general", capture_input=False, capture_output=False)
    def process(
        self,
        audio: bytes,
        *,
        elder_id: str,
        external_id: str = "",
        channel: str = "",
        content_type: str = "audio/m4a",
        trace_id: str = "",
        audio_url: str = "",
    ) -> TtsResult:
        tracing.tag_current_trace(trace_id=trace_id, channel=channel, elder_id=elder_id)
        user_text = self._transcribe(
            audio,
            content_type=content_type,
            external_id=external_id,
            channel=channel,
            trace_id=trace_id,
            audio_url=audio_url,
        )
        return self._process_transcribed(
            user_text,
            elder_id=elder_id,
            external_id=external_id,
            channel=channel,
            trace_id=trace_id,
        )
```
為 `process_text` 加裝飾器與標記：
```python
    @tracing.track(name="care_turn_text", type="general", capture_input=False, capture_output=False)
    def process_text(
        self,
        text: str,
        *,
        elder_id: str,
        external_id: str = "",
        channel: str = "",
        trace_id: str = "",
    ) -> TtsResult:
        """文字輸入路徑（✅ D-11 正式）：跳過 ASR，其餘與語音同管線（危急偵測＋回覆＋記憶）。"""
        tracing.tag_current_trace(trace_id=trace_id, channel=channel, elder_id=elder_id)
        return self._process_transcribed(
            text, elder_id=elder_id, external_id=external_id, channel=channel, trace_id=trace_id
        )
```

- [ ] **Step 4: 為四個階段方法加 span 裝飾器**

在 `src/kinsun/pipeline.py` 各方法定義前加裝飾器（僅結構性 span——LLM 內容由 track_genai 自動捕捉，故 `capture_input/output=False` 避免抓到 self/bytes/PII）：
```python
    @tracing.track(name="asr", type="general", capture_input=False, capture_output=False)
    def _transcribe(self, audio: bytes, *, content_type: str, external_id: str, channel: str, trace_id: str, audio_url: str) -> str:
```
```python
    @tracing.track(name="risk_assess", type="general", capture_input=False, capture_output=False)
    def _assess(self, user_text: str, *, external_id: str, channel: str, trace_id: str) -> RiskAssessment:
```
```python
    @tracing.track(name="agent_generate", type="llm", capture_input=False, capture_output=False)
    def _generate(self, elder_id: str, user_text: str, *, external_id: str, channel: str, trace_id: str) -> str:
```
```python
    @tracing.track(name="tts", type="general", capture_input=False, capture_output=False)
    def _synthesize(self, reply_text: str, *, external_id: str, channel: str, trace_id: str) -> TtsResult:
```
（只加裝飾器行，方法內容不動。）

- [ ] **Step 5: 執行全 pipeline 測試確認守恆**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_pipeline.py -q`
Expected: PASS（停用時裝飾器為 no-op，既有斷言全數不變）。

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): emit Opik spans per stage and tag trace with kinsun trace_id"
```

---

### Task 8：深度 span — 工具呼叫與 RAG 檢索

**Files:**
- Modify: `src/kinsun/tools/registry.py`（`dispatch`）
- Modify: `src/kinsun/rag/retriever.py`（檢索方法）
- Test: `tests/test_tools_registry.py`（或既有對應測試）

**Interfaces:**
- Consumes: `kinsun.tracing.track`
- Produces: 每次工具呼叫、每次 RAG 檢索各一 span（含輸入/輸出，供 debug 與 ContextPrecision 評測）。

- [ ] **Step 1: 確認 dispatch 與 retriever 方法簽章**

Run:
```bash
grep -n "def dispatch" src/kinsun/tools/registry.py
grep -nE "def (retrieve|search)" src/kinsun/rag/retriever.py
```
Expected: 找到 `dispatch(self, name, arguments)` 與檢索方法名（下步依實際名套用）。

- [ ] **Step 2: 寫守恆測試**

在對應測試檔（如 `tests/test_tools_registry.py`；若無則新增）加一個「停用時 dispatch 行為不變」的測試：
```python
def test_dispatch_unchanged_when_tracing_disabled():
    from kinsun.tracing import client as tracing_client

    tracing_client.reset_for_test()
    # 沿用既有 registry 建構樣式註冊一個假工具，斷言回傳值與未加裝飾前一致。
    ...
```

- [ ] **Step 3: 加裝飾器**

`src/kinsun/tools/registry.py` 頂部加 `from kinsun import tracing`，於 `dispatch` 前：
```python
    @tracing.track(type="tool", capture_input=True, capture_output=True)
    def dispatch(self, name, arguments):
```
`src/kinsun/rag/retriever.py` 頂部加 `from kinsun import tracing`，於檢索方法前（以實際方法名為準）：
```python
    @tracing.track(name="rag_retrieve", type="general", capture_input=True, capture_output=True)
    def retrieve(self, query, ...):
```

- [ ] **Step 4: 執行確認通過**

Run: `cd /home/leo29/kinsun && uv run pytest tests/test_tools_registry.py tests/ -k "rag or tool or retriev" -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/kinsun/tools/registry.py src/kinsun/rag/retriever.py tests/test_tools_registry.py
git commit -m "feat(tracing): add tool-call and RAG-retrieval spans"
```

---

## Phase 3：離線評測 + 文檔同步

### Task 9：evals — 幻覺與 RAG 品質離線評測

**Files:**
- Create: `evals/README.md`、`evals/datasets/careline_smoke.py`、`evals/experiments/hallucination.py`

**Interfaces:**
- Consumes: `opik`（Dataset、evaluate、metrics）、`kinsun.tracing.configure`、`kinsun.config.load_settings`
- Produces: 可重跑的離線評測腳本，把長照問答資料集上傳 Opik、對 Gemini 產生答案跑 Hallucination 指標。

- [ ] **Step 1: 建資料集腳本**

Create `evals/datasets/careline_smoke.py`:
```python
"""最小長照問答冒煙資料集：上傳成 Opik dataset，供實驗重複使用。"""

from __future__ import annotations

import opik

DATASET_NAME = "kinsun-careline-smoke"

ITEMS = [
    {"input": "阿嬤問她高血壓可以吃柚子嗎", "expected_output": "提醒柚子與部分降血壓藥會交互作用，建議先問醫師或藥師，不要自行決定。"},
    {"input": "阿公說他忘記今天吃過藥沒", "expected_output": "溫和安撫，建議看藥盒或問家人，不要重複服藥。"},
    {"input": "長輩問附近有什麼好玩的", "expected_output": "口語閒聊式回應，不編造不存在的地點。"},
]


def seed() -> None:
    client = opik.Opik()
    dataset = client.get_or_create_dataset(name=DATASET_NAME)
    dataset.insert(ITEMS)
    print(f"已上傳 {len(ITEMS)} 筆到 Opik dataset：{DATASET_NAME}")


if __name__ == "__main__":
    seed()
```

- [ ] **Step 2: 建實驗腳本**

Create `evals/experiments/hallucination.py`:
```python
"""對長照冒煙資料集跑 Gemini，並以 Opik Hallucination 指標評分。"""

from __future__ import annotations

import os

import opik
from opik.evaluation import evaluate
from opik.evaluation.metrics import Hallucination

from evals.datasets.careline_smoke import DATASET_NAME
from kinsun import tracing
from kinsun.config import load_settings
from kinsun.llm import build_gemini_for
from kinsun.llm import Message


def _task(item: dict) -> dict:
    settings = load_settings(os.environ)
    gemini = build_gemini_for(settings, settings.gemini_model, client_wrapper=tracing.wrap_genai)
    reply = gemini.generate(system_prompt="你是金孫長輩陪伴助理，只講台灣口語短句。", messages=[Message("user", item["input"])])
    return {"output": reply}


def main() -> None:
    settings = load_settings(os.environ)
    tracing.configure(settings)  # 需 OPIK_ENABLED=true
    client = opik.Opik()
    dataset = client.get_dataset(name=DATASET_NAME)
    evaluate(
        dataset=dataset,
        task=_task,
        scoring_metrics=[Hallucination()],
        experiment_name="careline-hallucination",
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 建 README**

Create `evals/README.md`：說明用途、前置（`OPIK_ENABLED=true`、Opik 服務在跑）、執行順序：
```markdown
# evals — Opik 離線評測

工程視角的離線品質關卡，不在請求路徑。需自架 Opik 在跑、且 `OPIK_ENABLED=true`。

## 執行
```bash
export OPIK_ENABLED=true
uv run python -m evals.datasets.careline_smoke     # 上傳資料集（一次）
uv run python -m evals.experiments.hallucination   # 跑實驗，結果見 http://localhost:5273
```
```

- [ ] **Step 4: 語法檢查（不連網）**

Run: `cd /home/leo29/kinsun && uv run python -c "import ast; [ast.parse(open(f).read()) for f in ['evals/datasets/careline_smoke.py','evals/experiments/hallucination.py']]; print('OK')"`
Expected: `OK`。

> 實際執行（Step 3 的指令）需 Opik 在跑且 `OPIK_ENABLED=true`，屬人工驗證，不進 CI。

- [ ] **Step 5: Commit**

```bash
git add evals/
git commit -m "feat(evals): add offline hallucination eval harness on Opik"
```

---

### Task 10：文檔同步（docs/dev 鐵律）

**Files:**
- Modify: `docs/dev/`（新增「工程觀測（Opik）」小節）、`docs/dev/README.md`（文件狀態表）

- [ ] **Step 1: 找對應文件**

Run:
```bash
ls docs/dev/
grep -rln "observability\|觀測\|環境變數" docs/dev/ | head
```
Expected: 找到記錄環境變數與系統模組的文件（依 `docs/dev/15_文檔與維護指南.md` §2 對照表）。

- [ ] **Step 2: 補一節**

在對應文件新增「工程觀測（Opik）」小節，內容涵蓋：兩視角分工（自建 observability＝業務、Opik＝工程/LLM 深度）、`kinsun.tracing` 模組職責與唯一 import opik 原則、`OPIK_` 四個環境變數、feature flag 語意、自架服務位置（`/home/leo29/opik`、`localhost:5273`）、`evals/` 用途。更新版頭版本/日期。

- [ ] **Step 3: 更新文件狀態表**

在 `docs/dev/README.md` 文件狀態表更新受影響文件的版本/日期。

- [ ] **Step 4: Commit**

```bash
git add docs/dev/
git commit -m "docs(dev): document Opik engineering-observability integration"
```

---

## 驗收（全部完成後）

- [ ] 全測試綠：`cd /home/leo29/kinsun && uv run pytest -q`
- [ ] 停用預設無影響：不設 `OPIK_ENABLED` 時，pipeline/llm/config 測試全過、行為與整合前一致。
- [ ] 端到端人工驗證（需 Opik 在跑）：`OPIK_ENABLED=true` 起 app，送一則測試訊息，於 `http://localhost:5273` 見到一條 trace，含 `care_turn_* → asr/risk_assess/agent_generate（下含 gemini 自動 span）/tts` 的巢狀結構，且 metadata 有 `kinsun_trace_id`。
- [ ] 自建後台不受影響：`observability` 五表照常寫入、admin API 照常回應。

---

## Self-Review（本計畫對照需求）

- **完整用 Opik**：trace + 巢狀 span（Task 7）、LLM 自動捕捉（Task 4+6）、工具/RAG span（Task 8）、離線評測含防幻覺（Task 9）、prompt/線上規則走 UI（文檔載明，Task 10）——涵蓋。
- **@track 哪些函式**：`process`/`process_text`（root）、`_transcribe`/`_assess`/`_generate`/`_synthesize`（stage）、`ToolRegistry.dispatch`、RAG 檢索——明列。
- **trace_id 怎麼傳**：既有 `trace_id` 參數不動，於 root 以 `tag_current_trace` 掛成 Opik trace metadata（Task 3、7）。
- **feature flag**：`OPIK_ENABLED` 於 `tracing.client` 統一守門，裝飾器延後到呼叫時判斷（Task 2、3）——避免 import 期定型的陷阱。
- **測試清單**：`test_config`、`test_tracing_client/decorators/genai`、`test_llm`、`test_composition`、`test_pipeline`、`test_tools_registry`——齊備，每個新行為都有守恆或行為測試。
- **無 placeholder**：每步含實際程式碼與可執行指令；Task 6/8 依實際簽章的步驟附 grep 先行確認。
