"""RAG golden set 門檻選擇與品質指標。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kinsun.rag.answer_policy import AnswerPolicy
from kinsun.rag.schemas import SearchResult


@dataclass(frozen=True)
class ThresholdMetrics:
    threshold: float
    supported_top3_recall: float
    unsupported_false_positive_rate: float


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    query: str
    kind: str
    expected_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoldenSetReport:
    threshold: float
    supported_top3_recall: float
    unsupported_false_positive_rate: float
    safety_pass_rate: float
    citation_correctness: float
    case_count: int


def select_relevance_threshold(
    candidates: tuple[ThresholdMetrics, ...],
) -> ThresholdMetrics:
    """先守門檻，再依 recall、false-positive、threshold 順序決勝。"""
    eligible = tuple(
        candidate
        for candidate in candidates
        if candidate.supported_top3_recall >= 0.8
        and candidate.unsupported_false_positive_rate <= 0.05
    )
    if not eligible:
        raise ValueError("沒有 relevance threshold 同時通過 recall 與 false-positive 門檻。")
    return max(
        eligible,
        key=lambda item: (
            item.supported_top3_recall,
            -item.unsupported_false_positive_rate,
            item.threshold,
        ),
    )


def load_golden_set(path: Path) -> tuple[GoldenCase, ...]:
    cases: list[GoldenCase] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            item = json.loads(line)
            cases.append(
                GoldenCase(
                    case_id=item["case_id"],
                    query=item["query"],
                    kind=item["kind"],
                    expected_source_ids=tuple(item.get("expected_source_ids", ())),
                )
            )
    return tuple(cases)


def evaluate_golden_set(
    retriever,
    cases: tuple[GoldenCase, ...],
    *,
    thresholds: tuple[float, ...] = tuple(value / 100 for value in range(20, 96, 5)),
) -> GoldenSetReport:
    retrieved: dict[str, tuple[SearchResult, ...]] = {
        case.case_id: retriever.retrieve(case.query, top_k=3)
        for case in cases
        if case.kind in {"supported", "unsupported"}
    }
    candidates = tuple(_measure_threshold(cases, retrieved, threshold) for threshold in thresholds)
    selected = select_relevance_threshold(candidates)
    safety_cases = tuple(case for case in cases if case.kind == "safety")
    safety_passes = sum(
        AnswerPolicy().build_answer(case.query, ()).requires_safety_attention
        for case in safety_cases
    )
    supported = tuple(case for case in cases if case.kind == "supported")
    citation_total = 0
    citation_correct = 0
    for case in supported:
        for result in _above_threshold(retrieved[case.case_id], selected.threshold):
            citation_total += 1
            metadata = result.chunk.metadata
            has_complete_citation = bool(
                metadata.source_id and metadata.title and metadata.publisher and metadata.source_url
            )
            matches_expected_source = (
                not case.expected_source_ids or metadata.source_id in case.expected_source_ids
            )
            if has_complete_citation and matches_expected_source:
                citation_correct += 1
    return GoldenSetReport(
        threshold=selected.threshold,
        supported_top3_recall=selected.supported_top3_recall,
        unsupported_false_positive_rate=selected.unsupported_false_positive_rate,
        safety_pass_rate=(safety_passes / len(safety_cases)) if safety_cases else 1.0,
        citation_correctness=(citation_correct / citation_total) if citation_total else 0.0,
        case_count=len(cases),
    )


def _measure_threshold(
    cases: tuple[GoldenCase, ...],
    retrieved: dict[str, tuple[SearchResult, ...]],
    threshold: float,
) -> ThresholdMetrics:
    supported = tuple(case for case in cases if case.kind == "supported")
    unsupported = tuple(case for case in cases if case.kind == "unsupported")
    supported_hits = sum(
        _is_supported_hit(
            case,
            _above_threshold(retrieved[case.case_id], threshold),
        )
        for case in supported
    )
    unsupported_hits = sum(
        bool(_above_threshold(retrieved[case.case_id], threshold)) for case in unsupported
    )
    return ThresholdMetrics(
        threshold=threshold,
        supported_top3_recall=(supported_hits / len(supported)) if supported else 1.0,
        unsupported_false_positive_rate=(
            unsupported_hits / len(unsupported) if unsupported else 0.0
        ),
    )


def _above_threshold(
    results: tuple[SearchResult, ...],
    threshold: float,
) -> tuple[SearchResult, ...]:
    return tuple(result for result in results if result.score >= threshold)[:3]


def _is_supported_hit(case: GoldenCase, results: tuple[SearchResult, ...]) -> bool:
    if not results:
        return False
    if not case.expected_source_ids:
        return True
    return any(result.chunk.metadata.source_id in case.expected_source_ids for result in results)
