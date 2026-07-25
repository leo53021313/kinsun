"""危急偵測 P/R 量測（✅ D-05 戊-4）：標注集載入驗證＋指標計算＋隨附資料集健檢。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kinsun.safety.evaluation import (
    DATASET_PATH,
    EvaluationError,
    LabeledUtterance,
    evaluate,
    format_report,
    keyword_only_assess,
    load_labeled_utterances,
)
from kinsun.safety.tiers import RiskAssessment, RiskTier


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path


# --- 載入與驗證 ---


def test_load_parses_text_tier_and_note(tmp_path):
    path = _write_jsonl(
        tmp_path / "labeled.jsonl",
        [
            {"text": "我想不開了", "tier": "L2", "note": "自殺意念"},
            {"text": "今天天氣真好", "tier": "L0"},
        ],
    )
    examples = load_labeled_utterances(path)
    assert examples[0] == LabeledUtterance("我想不開了", RiskTier.L2, "自殺意念")
    assert examples[1].expected == RiskTier.L0
    assert examples[1].note == ""


def test_load_rejects_unknown_tier(tmp_path):
    path = _write_jsonl(tmp_path / "labeled.jsonl", [{"text": "嗨", "tier": "L3"}])
    with pytest.raises(EvaluationError, match="tier"):
        load_labeled_utterances(path)


def test_load_rejects_empty_text_and_duplicates(tmp_path):
    with pytest.raises(EvaluationError, match="text"):
        load_labeled_utterances(_write_jsonl(tmp_path / "a.jsonl", [{"text": "  ", "tier": "L0"}]))
    with pytest.raises(EvaluationError, match="重複"):
        load_labeled_utterances(
            _write_jsonl(
                tmp_path / "b.jsonl",
                [{"text": "嗨", "tier": "L0"}, {"text": "嗨", "tier": "L1"}],
            )
        )


def test_load_skips_blank_lines_and_comments(tmp_path):
    path = tmp_path / "labeled.jsonl"
    path.write_text('\n# 註解\n{"text": "嗨", "tier": "L0"}\n\n', encoding="utf-8")
    assert len(load_labeled_utterances(path)) == 1


# --- 指標計算 ---


def _stub_assess(mapping: dict[str, RiskTier]):
    def assess(text: str) -> RiskAssessment:
        return RiskAssessment(mapping[text], 0.9, "stub", [])

    return assess


def test_evaluate_alert_precision_recall_and_missed():
    """通報層（≥L2）二元 P/R 為 KPI 主指標；漏報清單顯式列出（漏報優先）。"""
    examples = [
        LabeledUtterance("A", RiskTier.L2),  # 命中
        LabeledUtterance("B", RiskTier.L2),  # 漏報
        LabeledUtterance("C", RiskTier.L0),  # 誤報
        LabeledUtterance("D", RiskTier.L2),  # 命中
    ]
    report = evaluate(
        _stub_assess({"A": RiskTier.L2, "B": RiskTier.L0, "C": RiskTier.L2, "D": RiskTier.L2}),
        examples,
    )
    assert report.total == 4
    assert report.alert_precision == pytest.approx(2 / 3)
    assert report.alert_recall == pytest.approx(2 / 3)
    assert [m.example.text for m in report.missed_alerts] == ["B"]
    assert report.missed_alerts[0].predicted == RiskTier.L0
    assert [m.example.text for m in report.false_alerts] == ["C"]


def test_evaluate_per_tier_counts_and_exact_accuracy():
    examples = [
        LabeledUtterance("A", RiskTier.L2),
        LabeledUtterance("B", RiskTier.L2),
        LabeledUtterance("C", RiskTier.L0),
    ]
    report = evaluate(
        _stub_assess({"A": RiskTier.L2, "B": RiskTier.L1, "C": RiskTier.L0}), examples
    )
    l2 = report.per_tier[RiskTier.L2]
    assert (l2.true_positive, l2.false_positive, l2.false_negative) == (1, 0, 1)
    assert l2.precision == 1.0
    assert l2.recall == 0.5
    assert report.exact_accuracy == pytest.approx(2 / 3)


def test_metrics_are_none_when_undefined():
    """分母為 0（該級無標注也無預測）時精確率／召回率為 None，報告顯示「—」。"""
    examples = [LabeledUtterance("A", RiskTier.L0)]
    report = evaluate(_stub_assess({"A": RiskTier.L0}), examples)
    assert report.per_tier[RiskTier.L2].precision is None
    assert report.per_tier[RiskTier.L2].recall is None
    assert "—" in format_report(report)


def test_format_report_mentions_alert_metrics():
    examples = [LabeledUtterance("A", RiskTier.L2)]
    report = evaluate(_stub_assess({"A": RiskTier.L2}), examples)
    text = format_report(report)
    assert "通報層" in text
    assert "召回率" in text
    assert "漏報" in text


# --- 離線 keyword-only 模式與隨附資料集 ---


def test_keyword_only_assess_matches_keyword_rules():
    assert keyword_only_assess("救命啊").tier == RiskTier.L2
    assert keyword_only_assess("我有點頭暈").tier == RiskTier.L2
    assert keyword_only_assess("今天天氣真好").tier == RiskTier.L0


def test_shipped_dataset_loads_and_covers_all_tiers():
    examples = load_labeled_utterances(DATASET_PATH)
    assert len(examples) >= 50
    tiers = {e.expected for e in examples}
    assert tiers == {RiskTier.L0, RiskTier.L1, RiskTier.L2}


def test_detector_builder_honours_model_override(monkeypatch):
    """`--model` 須真的傳到 GeminiClient——否則比較三個模型會全部跑到同一顆。

    這種錯誤不會報錯、只會讓三次結果長得一樣，很容易被當成「模型沒差」而下錯結論。
    """
    from kinsun.safety import evaluation

    captured: dict[str, str] = {}

    class _SpyGeminiClient:
        def __init__(self, *, api_key, model, timeout):
            captured["model"] = model

        def generate(self, **kwargs):  # pragma: no cover - 本測試不呼叫
            return ""

    monkeypatch.setattr("kinsun.llm.GeminiClient", _SpyGeminiClient)
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    evaluation._build_detector_assess("gemini-3.5-pro")
    assert captured["model"] == "gemini-3.5-pro"


def test_detector_builder_defaults_to_configured_safety_model(monkeypatch):
    """留空＝沿用 GEMINI_MODEL_SAFETY（正式設定），不可變成硬編碼。"""
    from kinsun.safety import evaluation

    captured: dict[str, str] = {}

    class _SpyGeminiClient:
        def __init__(self, *, api_key, model, timeout):
            captured["model"] = model

        def generate(self, **kwargs):  # pragma: no cover
            return ""

    monkeypatch.setattr("kinsun.llm.GeminiClient", _SpyGeminiClient)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL_SAFETY", "gemini-from-env")

    evaluation._build_detector_assess()
    assert captured["model"] == "gemini-from-env"
