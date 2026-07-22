"""對 Opik 裡的真實對話 thread 做「對話串級」評測（不只單輪）。

長輩陪伴是多輪對話。這支用 opik 的 evaluate_threads 撈 kinsun 專案的真實 thread
（app 已以 elder_id 當 thread_id 串起、set_current_trace_io 寫入每輪對話內容），
還原成多輪對話後以 LLM-judge 評：

- ConversationalCoherence＝整段對話前後連不連貫。
- UserFrustration＝長輩在這段對話裡有沒有顯得挫折／被惹毛。
- SessionCompletenessQuality＝這段對話有沒有把長輩的需求好好收尾。

不在請求路徑。前置：OPIK_ENABLED=true、自架 Opik 在跑、GEMINI_API_KEY 已設。
詳見 evals/README.md。
"""

from __future__ import annotations

import os

from opik.evaluation import evaluate_threads
from opik.evaluation.metrics import (
    ConversationalCoherenceMetric,
    SessionCompletenessQuality,
    UserFrustrationMetric,
)

from evals._support import build_judge
from kinsun import tracing
from kinsun.config import load_dotenv, load_settings

# 只評夠長的 thread，跳過遷移／測試殘留的極短 thread。
_MIN_MESSAGES = 4
# 每條 thread 最多取幾則 trace 進評測，控制 LLM 成本（避免超長 thread 爆量）。
_MAX_TRACES_PER_THREAD = 20


def _turn_text(payload) -> str:
    """把一條 trace 的 input/output 還原成一句對話文字；非對話 trace（無 text）回空字串。"""
    if isinstance(payload, dict):
        return str(payload.get("text", "") or "")
    if isinstance(payload, str):
        return payload
    return ""


def main() -> None:
    load_dotenv()  # 標準入口慣例：先把 .env 補進環境（GEMINI_API_KEY 等）
    settings = load_settings(os.environ)
    tracing.configure(settings)  # 需 OPIK_ENABLED=true
    judge = build_judge(settings.gemini_model)
    result = evaluate_threads(
        project_name=settings.opik_project_name,
        filter_string=f"number_of_messages >= {_MIN_MESSAGES}",
        # 評測 trace 另存專屬專案，保持 kinsun 主專案乾淨；分數仍會掛回原 thread。
        eval_project_name=f"{settings.opik_project_name}-thread-evals",
        metrics=[
            ConversationalCoherenceMetric(model=judge),
            UserFrustrationMetric(model=judge),
            SessionCompletenessQuality(model=judge),
        ],
        trace_input_transform=_turn_text,
        trace_output_transform=_turn_text,
        num_workers=1,  # 序列化：對 Gemini 免費層 RPM 限流較友善
        max_traces_per_thread=_MAX_TRACES_PER_THREAD,
    )
    print(result)


if __name__ == "__main__":
    main()
