"""對長照冒煙資料集跑 Gemini，並以 Opik Hallucination 指標評分。

需 OPIK_ENABLED=true 且自架 Opik 在跑（見 evals/README.md）。
"""

from __future__ import annotations

import os

import opik
from opik.evaluation import evaluate
from opik.evaluation.metrics import Hallucination

from evals.datasets.careline_smoke import DATASET_NAME
from kinsun import tracing
from kinsun.config import load_settings
from kinsun.llm import Message, build_gemini_for

_SYSTEM_PROMPT = "你是金孫，一位溫暖的台灣長輩陪伴助理，只講台灣口語短句，不編造事實。"


def _task(item: dict) -> dict:
    settings = load_settings(os.environ)
    gemini = build_gemini_for(
        settings, settings.gemini_model, client_wrapper=tracing.wrap_genai
    )
    reply = gemini.generate(
        system_prompt=_SYSTEM_PROMPT, messages=[Message("user", item["input"])]
    )
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
