"""evals 共用工具：讓實驗在 Gemini 免費層 RPM 限流下也能整批跑完。

- build_judge：建 LLM-judge 裁判模型，指定 Gemini 並帶 litellm num_retries（遇 429 自動退避）。
- with_retry：包裝 task 端的 Gemini 呼叫，遇限流以線性退避重試（RPM 每分鐘重置）。
"""

from __future__ import annotations

import time
from collections.abc import Callable

from opik.evaluation.models.litellm.litellm_chat_model import LiteLLMChatModel


def build_judge(gemini_model: str, *, num_retries: int = 8) -> LiteLLMChatModel:
    """LLM-judge 裁判：Opik 指標預設走 OpenAI，這裡改用 Gemini（讀 GEMINI_API_KEY）。

    completion_kwargs 的 num_retries 讓 litellm 對 429 自動退避重試，緩解免費層限流。
    """
    return LiteLLMChatModel(
        model_name=f"gemini/{gemini_model}",
        completion_kwargs={"num_retries": num_retries},
    )


def with_retry[T](fn: Callable[[], T], *, attempts: int = 8, base_delay: float = 10.0) -> T:
    """執行 fn，遇任何例外（多為 429 限流）以線性退避重試；用盡則拋最後一個例外。"""
    last_exc: Exception | None = None
    for index in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 限流／暫時性錯誤都重試
            last_exc = exc
            if index == attempts - 1:
                raise
            time.sleep(base_delay * (index + 1))
    raise last_exc  # pragma: no cover - 迴圈必先 return 或 raise
