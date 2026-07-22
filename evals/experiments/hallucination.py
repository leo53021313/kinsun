"""對長照冒煙資料集跑 Gemini，並以 Opik Hallucination＋Moderation 指標評分。

Hallucination＝防幻覺（有沒有編造）、Moderation＝內容審核（有沒有不當／有害內容）。
需 OPIK_ENABLED=true 且自架 Opik 在跑（見 evals/README.md）。
"""

from __future__ import annotations

import os

import opik
from opik.evaluation import evaluate
from opik.evaluation.metrics import Hallucination, Moderation

from evals._support import build_judge, with_retry
from evals.datasets.careline_smoke import DATASET_NAME
from kinsun import tracing
from kinsun.config import load_dotenv, load_settings
from kinsun.llm import Message, build_gemini_for

_SYSTEM_PROMPT = "你是金孫，一位溫暖的台灣長輩陪伴助理，只講台灣口語短句，不編造事實。"


def main() -> None:
    load_dotenv()  # 標準入口慣例：先把 .env 補進環境（GEMINI_API_KEY 等）
    settings = load_settings(os.environ)
    tracing.configure(settings)  # 需 OPIK_ENABLED=true
    gemini = build_gemini_for(settings, settings.gemini_model, client_wrapper=tracing.wrap_genai)

    def _task(item: dict) -> dict:
        reply = with_retry(
            lambda: gemini.generate(
                system_prompt=_SYSTEM_PROMPT, messages=[Message("user", item["input"])]
            )
        )
        return {"output": reply}

    judge = build_judge(settings.gemini_model)
    client = opik.Opik()
    dataset = client.get_dataset(name=DATASET_NAME)
    evaluate(
        dataset=dataset,
        task=_task,
        scoring_metrics=[Hallucination(model=judge), Moderation(model=judge)],
        experiment_name="careline-quality",
        task_threads=1,  # 序列化：對 Gemini 免費層 RPM 限流較友善
    )


if __name__ == "__main__":
    main()
