"""危急偵測 P/R 量測（✅ D-05 戊-4）：標注集 → 偵測器 → 精確率／召回率報告。

標注集為 JSONL（`data/safety_eval/labeled_utterances.jsonl`），每行
`{"text": …, "tier": "L0|L1|L2|L3", "note": …}`；標注為草案，實測期由團隊
滾動修訂（會-6 詞表、會-7 門檻都以本工具的數字為依據）。

CLI（量測用，不進正式服務）：
- 離線詞表模式：`PYTHONPATH=src uv run python -m kinsun.safety.evaluation --keyword-only`
- 完整偵測器（需 GEMINI_API_KEY）：`PYTHONPATH=src uv run python -m kinsun.safety.evaluation`
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from kinsun.safety.keywords import classify_keywords
from kinsun.safety.tiers import RiskAssessment, RiskTier

DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "safety_eval" / "labeled_utterances.jsonl"
)

# 通報層門檻：達此級即通知家屬（與 pipeline 的通知條件一致）。
ALERT_TIER = RiskTier.L2


class EvaluationError(Exception):
    """標注集格式錯誤。"""


@dataclass(frozen=True)
class LabeledUtterance:
    text: str
    expected: RiskTier
    note: str = ""


@dataclass(frozen=True)
class Misclassified:
    example: LabeledUtterance
    predicted: RiskTier


@dataclass(frozen=True)
class TierMetrics:
    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def precision(self) -> float | None:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else None

    @property
    def recall(self) -> float | None:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else None


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    exact_match: int
    per_tier: dict[RiskTier, TierMetrics]
    # 通報層（≥L2）二元指標＝KPI 主指標；漏報清單顯式列出（漏報優先）。
    alert_true_positive: int
    alert_false_positive: int
    alert_false_negative: int
    missed_alerts: list[Misclassified] = field(default_factory=list)
    false_alerts: list[Misclassified] = field(default_factory=list)

    @property
    def exact_accuracy(self) -> float | None:
        return self.exact_match / self.total if self.total else None

    @property
    def alert_precision(self) -> float | None:
        denominator = self.alert_true_positive + self.alert_false_positive
        return self.alert_true_positive / denominator if denominator else None

    @property
    def alert_recall(self) -> float | None:
        denominator = self.alert_true_positive + self.alert_false_negative
        return self.alert_true_positive / denominator if denominator else None


def load_labeled_utterances(path: Path) -> list[LabeledUtterance]:
    if not path.is_file():
        raise EvaluationError(f"找不到標注集：{path}")
    examples: list[LabeledUtterance] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationError(f"第 {line_number} 行不是合法 JSON：{exc}") from exc
        text = str(row.get("text", "")).strip()
        if not text:
            raise EvaluationError(f"第 {line_number} 行缺 text（或為空白）")
        tier_name = str(row.get("tier", ""))
        if tier_name not in RiskTier.__members__:
            raise EvaluationError(f"第 {line_number} 行 tier 不合法：{tier_name!r}（需 L0–L2）")
        if text in seen:
            raise EvaluationError(f"第 {line_number} 行 text 重複：{text!r}")
        seen.add(text)
        examples.append(LabeledUtterance(text, RiskTier[tier_name], str(row.get("note", ""))))
    return examples


def keyword_only_assess(text: str) -> RiskAssessment:
    """離線詞表模式：只跑 classify_keywords，不需 LLM——量詞表本身的涵蓋率。"""
    tier, is_absolute = classify_keywords(text)
    signal = "keyword:absolute" if is_absolute else "keyword:symptom"
    return RiskAssessment(tier, 1.0, "詞表模式", [signal] if tier > RiskTier.L0 else [])


def evaluate(
    assess: Callable[[str], RiskAssessment], examples: Iterable[LabeledUtterance]
) -> EvaluationReport:
    counts = {tier: [0, 0, 0] for tier in RiskTier}  # [TP, FP, FN]
    exact_match = 0
    total = 0
    alert_tp = alert_fp = alert_fn = 0
    missed: list[Misclassified] = []
    false_alerts: list[Misclassified] = []
    for example in examples:
        total += 1
        predicted = assess(example.text).tier
        if predicted == example.expected:
            exact_match += 1
            counts[predicted][0] += 1
        else:
            counts[predicted][1] += 1
            counts[example.expected][2] += 1
        expected_alert = example.expected >= ALERT_TIER
        predicted_alert = predicted >= ALERT_TIER
        if expected_alert and predicted_alert:
            alert_tp += 1
        elif not expected_alert and predicted_alert:
            alert_fp += 1
            false_alerts.append(Misclassified(example, predicted))
        elif expected_alert and not predicted_alert:
            alert_fn += 1
            missed.append(Misclassified(example, predicted))
    return EvaluationReport(
        total=total,
        exact_match=exact_match,
        per_tier={tier: TierMetrics(*counts[tier]) for tier in RiskTier},
        alert_true_positive=alert_tp,
        alert_false_positive=alert_fp,
        alert_false_negative=alert_fn,
        missed_alerts=missed,
        false_alerts=false_alerts,
    )


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def format_report(report: EvaluationReport) -> str:
    lines = [
        f"標注數：{report.total}　層級全對率：{_pct(report.exact_accuracy)}",
        "",
        f"通報層（≥{ALERT_TIER.name}，通知家屬與否）：",
        f"  精確率 {_pct(report.alert_precision)}　召回率 {_pct(report.alert_recall)}"
        f"（漏報 {report.alert_false_negative}、誤報 {report.alert_false_positive}）",
        "",
        "各級（one-vs-rest）：",
    ]
    for tier, metrics in report.per_tier.items():
        lines.append(
            f"  {tier.name}：精確率 {_pct(metrics.precision)}　召回率 {_pct(metrics.recall)}"
            f"（TP {metrics.true_positive}／FP {metrics.false_positive}"
            f"／FN {metrics.false_negative}）"
        )
    if report.missed_alerts:
        lines += ["", "⚠️ 漏報清單（標注應通報、實際未達通報層）："]
        lines += [
            f"  [{m.example.expected.name}→{m.predicted.name}] {m.example.text}"
            + (f"（{m.example.note}）" if m.example.note else "")
            for m in report.missed_alerts
        ]
    if report.false_alerts:
        lines += ["", "誤報清單（標注不需通報、實際達通報層）："]
        lines += [
            f"  [{m.example.expected.name}→{m.predicted.name}] {m.example.text}"
            for m in report.false_alerts
        ]
    return "\n".join(lines)


def _build_detector_assess() -> Callable[[str], RiskAssessment]:
    """完整偵測器（LLM＋詞表＋門檻）：與 app.py 同一組裝，需 GEMINI_API_KEY。"""
    import os

    from kinsun.config import load_dotenv, load_settings
    from kinsun.llm import GeminiClient
    from kinsun.safety.classifier import LlmRiskClassifier
    from kinsun.safety.detector import RiskDetector

    load_dotenv()
    settings = load_settings(os.environ)
    detector = RiskDetector(
        LlmRiskClassifier(
            GeminiClient(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model_safety,
                timeout=settings.gemini_timeout_seconds,
            )
        ),
        mid=settings.safety_confidence_mid,
    )
    return detector.assess


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="危急偵測 P/R 量測（D-05 KPI）")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH, help="標注集 JSONL 路徑")
    parser.add_argument(
        "--keyword-only",
        action="store_true",
        help="只量詞表（離線、不需 GEMINI_API_KEY）",
    )
    args = parser.parse_args(argv)
    examples = load_labeled_utterances(args.dataset)
    assess = keyword_only_assess if args.keyword_only else _build_detector_assess()
    mode = "詞表模式" if args.keyword_only else "完整偵測器（LLM＋詞表）"
    print(f"模式：{mode}　標注集：{args.dataset}")
    print(format_report(evaluate(assess, examples)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
