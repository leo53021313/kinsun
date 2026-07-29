"""危急偵測 P/R 量測（✅ D-05 戊-4）：標注集 → 偵測器 → 精確率／召回率報告。

標注集為 JSONL（`data/safety_eval/labeled_utterances.jsonl`），每行
`{"text": …, "tier": "L0|L1|L2", "note": …}`（三級制 ✅ D-72；舊標注 L3 讀取時夾回
L2）；標注為草案，實測期由團隊
滾動修訂（會-6 詞表、會-7 門檻都以本工具的數字為依據）。

CLI（量測用，不進正式服務）：
- 離線詞表模式：`PYTHONPATH=src uv run python -m kinsun.safety.evaluation --keyword-only`
- 完整偵測器（需 GEMINI_API_KEY）：`PYTHONPATH=src uv run python -m kinsun.safety.evaluation`
- 模型選型比較（2026-07-25）：同一份標注集換模型各跑一次，比對 P/R——

      for m in gemini-3.5-flash-lite gemini-3.5-flash gemini-3.5-pro; do
        PYTHONPATH=src uv run python -m kinsun.safety.evaluation --model "$m"
      done

  `GEMINI_MODEL_SAFETY` 自 D-16 設好就沒被驗證過，而危急分級**漏報是會出人命的**，
  選型該有數字支撐而不是沿用預設值。看數字時以**召回率（漏報）優先**於精確率——
  誤報只是多吵家屬一次，漏報是沒人去救。注意每跑一次都會消耗完整標注集的 API 額度。
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
    # 分級器失敗（`llm:error`）的句數。⚠️ 這一格存在的理由見 `evaluate` 的註解：
    # 沒有它，整份報表可能量的是「純詞表＋fail-safe」而讀的人看不出來。
    degraded: int = 0

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
    degraded = 0
    for example in examples:
        total += 1
        assessment = assess(example.text)
        predicted = assessment.tier
        # ⚠️ **必須看 signals，不能只取 tier**（2026-07-29）。
        # `RiskDetector` 的 fail-safe 是刻意設計：分級器一掛，症狀詞照舊撐住 L2、
        # 其餘保守記 L1，好讓真的求救不會因為 LLM 故障而漏掉。但那代表 LLM 全掛時，
        # 這支工具量到的其實是「純詞表＋fail-safe」的成績——而原本的報表完全看不出來。
        # 實測撞過：同一份標注集，一次完整跑報「誤報 7」，逐句直呼偵測器卻是正確的 L1，
        # 差別只在那一輪有呼叫失敗。看到「召回率 100%」的人會以為分級器很好，它沒跑。
        if "llm:error" in assessment.signals:
            degraded += 1
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
        degraded=degraded,
    )


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def format_report(report: EvaluationReport) -> str:
    lines: list[str] = []
    if report.degraded:
        # ⚠️ 擺在**最前面**且用滿版警示：這份報表會被拿來決定要不要換模型、要不要調門檻。
        # 降級的數字如果只是夾在一行小字裡會被略過，而略過的代價是拿詞表的成績去做
        # 分級器的決策——那正是「看起來是綠的」比沒有告警更危險的情形。
        lines += [
            "=" * 66,
            f"⚠️  本次有 {report.degraded}/{report.total} 句**降級**判定"
            "——分級器失敗，走了 fail-safe（llm:error）。",
            "    那些句子量到的是「純詞表＋fail-safe」，不是分級器的成績。",
            "    以下數字不可用於模型選型或門檻調整——請先排除失敗原因再重跑。",
            "=" * 66,
            "",
        ]
    lines += [
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


def _build_detector_assess(model: str = "") -> Callable[[str], RiskAssessment]:
    """完整偵測器（LLM＋詞表＋門檻）：與 app.py 同一組裝，需 GEMINI_API_KEY。

    model 留空＝用 `GEMINI_MODEL_SAFETY`（正式設定）。傳入模型名可跑同一份標注集比較
    不同模型的 P/R——`GEMINI_MODEL_SAFETY` 自 D-16 設好就沒被驗證過，而危急分級漏報
    是會出人命的，選型該有數字支撐而不是沿用預設值。
    """
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
                model=model or settings.gemini_model_safety,
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
    parser.add_argument(
        "--model",
        default="",
        help="覆寫分級模型（留空＝用 GEMINI_MODEL_SAFETY）。同一份標注集換模型跑，即可比較 P/R",
    )
    args = parser.parse_args(argv)
    examples = load_labeled_utterances(args.dataset)
    assess = keyword_only_assess if args.keyword_only else _build_detector_assess(args.model)
    mode = "詞表模式" if args.keyword_only else "完整偵測器（LLM＋詞表）"
    if args.model and not args.keyword_only:
        mode += f"　模型：{args.model}"
    print(f"模式：{mode}　標注集：{args.dataset}")
    print(format_report(evaluate(assess, examples)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
