"""promptfoo 的確定性 assertion：這則回覆能不能直接唸給長輩聽。

規則本體在 `evals/assertions.check_speakable`，與 Opik 評測共用同一份——兩邊各寫一份
規則，遲早會變成「同一句話在兩支評測拿到不同結論」。

用法（`promptfooconfig.yaml`）：

    assert:
      - type: python
        value: file://assert_speakable.py

不呼叫 LLM，故不吃 API 額度、不受免費層限流影響，可以放心進 CI。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals.assertions import check_speakable  # noqa: E402


def get_assert(output: str, context: Any = None) -> dict[str, Any]:
    """promptfoo 的 Python assertion 介面：回 GradingResult（pass／score／reason）。"""
    result = check_speakable(output)
    return {
        "pass": result.is_speakable,
        "score": 1.0 if result.is_speakable else 0.0,
        "reason": result.reason,
    }
