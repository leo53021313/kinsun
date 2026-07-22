"""對衛教問答資料集實跑「真實 RAG 檢索」，評檢索與回答品質。

每筆問題會真的呼叫線上同款的 HealthEducationRagService（真實 retriever ＋ Gemini 改寫），
把當次檢索到的 evidence 當 context 交給指標評分：

- ContextPrecision＝檢索到的資料有多少是相關的（雜訊多不多）。
- ContextRecall＝該找到的相關資料有沒有漏掉。
- AnswerRelevance＝最終回答有沒有切題。

前置：OPIK_ENABLED=true、自架 Opik 在跑、DATABASE_URL 指向含 active release 的衛教
向量庫、GEMINI_API_KEY 已設（檢索 embedding 與答案改寫都會呼叫 Gemini）。詳見 evals/README.md。
"""

from __future__ import annotations

import os

import opik
from opik.evaluation import evaluate
from opik.evaluation.metrics import AnswerRelevance, ContextPrecision, ContextRecall

from evals._support import build_judge
from evals.datasets.health_rag import DATASET_NAME
from kinsun import tracing
from kinsun.config import load_dotenv, load_settings
from kinsun.db import Database
from kinsun.llm import build_gemini_for
from kinsun.rag.embeddings import GeminiEmbeddingModel
from kinsun.rag.retriever import HealthEducationRetriever
from kinsun.rag.service import HealthEducationRagService
from kinsun.rag.vector_store import PgVectorStore


def _build_rag_service(settings, db: Database) -> HealthEducationRagService:
    """比照 composition.build_externals 組真實 RAG 服務（同一份檢索與改寫路徑）。"""
    retriever = HealthEducationRetriever(
        vector_store=PgVectorStore(db),
        embedding_model=GeminiEmbeddingModel(
            api_key=settings.gemini_api_key,
            model=settings.rag_embedding_model,
            request_timeout_seconds=settings.gemini_timeout_seconds,
        ),
    )
    gemini = build_gemini_for(settings, settings.gemini_model, client_wrapper=tracing.wrap_genai)
    return HealthEducationRagService(retriever, llm=gemini, top_k=settings.rag_top_k)


def main() -> None:
    load_dotenv()  # 標準入口慣例：先把 .env 補進環境（GEMINI_API_KEY／DATABASE_URL 等）
    settings = load_settings(os.environ)
    tracing.configure(settings)  # 需 OPIK_ENABLED=true
    db = Database.open(settings.database_url, max_size=settings.database_pool_max_size)
    service = _build_rag_service(settings, db)

    def _task(item: dict) -> dict:
        answer = service.answer(item["input"])
        # context＝這次回答實際採用的 evidence 原文（單次檢索，與回答對齊）。
        context = [result.chunk.text for result in answer.evidence]
        return {"output": answer.answer, "context": context}

    # LLM-judge 指標預設走 OpenAI；本專案用 Gemini（帶 num_retries 緩解免費層限流）。
    judge = build_judge(settings.gemini_model)
    try:
        client = opik.Opik()
        dataset = client.get_dataset(name=DATASET_NAME)
        evaluate(
            dataset=dataset,
            task=_task,
            scoring_metrics=[
                ContextPrecision(model=judge),
                ContextRecall(model=judge),
                # require_context=False：檢索空手時仍評「答案切不切題」，不硬失敗。
                AnswerRelevance(model=judge, require_context=False),
            ],
            experiment_name="careline-rag-grounding",
            task_threads=1,  # 序列化：對 Gemini 免費層 RPM 限流較友善
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
