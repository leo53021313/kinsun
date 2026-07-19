import pytest

from kinsun.rag.evaluation import ThresholdMetrics, select_relevance_threshold
from kinsun.rag.releases import QualityGateInput, evaluate_quality_gate


def _clean_structural_metrics(document_count: int = 10) -> dict[str, int]:
    return {
        "document_count": document_count,
        "chunk_count": 20,
        "empty_embedding_count": 0,
        "overlong_chunk_count": 0,
        "empty_chunk_count": 0,
        "duplicate_url_count": 0,
        "duplicate_content_hash_count": 0,
        "orphan_document_count": 0,
        "orphan_chunk_count": 0,
    }


def test_quality_gate_passes_complete_release():
    result = evaluate_quality_gate(
        _clean_structural_metrics(),
        QualityGateInput(
            attempted_documents=10,
            failed_documents=1,
            safety_pass_rate=1,
            supported_top3_recall=0.8,
            unsupported_false_positive_rate=0.05,
            citation_correctness=1,
            relevance_threshold=0.72,
        ),
        previous_document_count=12,
    )

    assert result.passed is True
    assert result.metrics["success_rate"] == 0.9


def test_quality_gate_reports_structural_and_evaluation_failures():
    structural = {**_clean_structural_metrics(document_count=7), "overlong_chunk_count": 1}

    result = evaluate_quality_gate(
        structural,
        QualityGateInput(
            attempted_documents=10,
            failed_documents=2,
            safety_pass_rate=0.9,
            supported_top3_recall=0.7,
            unsupported_false_positive_rate=0.1,
            citation_correctness=0.8,
            relevance_threshold=0.5,
        ),
        previous_document_count=10,
    )

    assert result.passed is False
    assert "文件數較前版下降超過 20%" in result.failures
    assert "有超長 chunk" in result.failures
    assert "安全案例未達 100%" in result.failures


def test_threshold_selection_uses_documented_tie_break_order():
    selected = select_relevance_threshold(
        (
            ThresholdMetrics(0.6, 0.8, 0.05),
            ThresholdMetrics(0.7, 0.9, 0.04),
            ThresholdMetrics(0.8, 0.9, 0.04),
        )
    )

    assert selected.threshold == 0.8


def test_threshold_selection_rejects_when_no_candidate_passes():
    with pytest.raises(ValueError, match="沒有 relevance threshold"):
        select_relevance_threshold((ThresholdMetrics(0.5, 0.7, 0.1),))
