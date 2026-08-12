"""驗證並彙整 Kinsun 長輩陪伴對話可用性測試資料。

本工具只處理去識別化的描述性研究資料，不推導統計顯著性、醫療結論或
未經研究者確認的產品洞察。

執行：
    python docs/uiux/prototype/tools/summarize_usability_results.py
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import date
from pathlib import Path

PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROTOTYPE_ROOT / "research" / "research-sessions.csv"
DEFAULT_OUTPUT = PROTOTYPE_ROOT / "research" / "research-summary.md"

REQUIRED_COLUMNS = (
    "participant_id",
    "session_date",
    "device",
    "font_scaling",
    "task_id",
    "completion",
    "assistance_level",
    "duration_seconds",
    "first_gesture",
    "error_count",
    "ease_score",
    "listening_correct",
    "thinking_correct",
    "speaking_correct",
    "error_recovery",
    "critical_issue",
    "observation",
)

TASK_LABELS = {
    "A": "自然開始對話",
    "B": "使用另一手勢",
    "C": "辨識系統狀態",
    "D": "連線錯誤回復",
}
COMPLETION_VALUES = {"completed", "not_completed"}
GESTURE_VALUES = {"", "tap", "hold", "undetermined"}
RECOGNITION_VALUES = {"", "yes", "no", "uncertain"}
RECOVERY_VALUES = {"", "reconnected", "returned_idle", "not_completed"}
CRITICAL_VALUES = {"yes", "no"}
PARTICIPANT_PATTERN = re.compile(r"P\d{2,3}")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
TAIWAN_MOBILE_PATTERN = re.compile(r"(?<!\d)09\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)")


class DataValidationError(ValueError):
    """表示研究資料不符合資料字典。"""


def _parse_integer(value: str, field: str, line_number: int) -> int | None:
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise DataValidationError(f"第 {line_number} 列：{field} 必須是整數。") from None


def _parse_number(value: str, field: str, line_number: int) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        raise DataValidationError(f"第 {line_number} 列：{field} 必須是數字。") from None


def _contains_obvious_pii(value: str) -> str | None:
    if EMAIL_PATTERN.search(value):
        return "電子郵件"
    if TAIWAN_MOBILE_PATTERN.search(value):
        return "台灣手機號碼"
    return None


def read_rows(path: Path) -> list[dict[str, str]]:
    """讀取 CSV、確認欄位並回傳已去除前後空白的資料列。"""

    if not path.is_file():
        raise DataValidationError(f"找不到研究資料：{path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        missing = [field for field in REQUIRED_COLUMNS if field not in fieldnames]
        if missing:
            raise DataValidationError(f"CSV 缺少必要欄位：{', '.join(missing)}")

        rows: list[dict[str, str]] = []
        for raw_row in reader:
            row = {field: (raw_row.get(field) or "").strip() for field in REQUIRED_COLUMNS}
            if any(row.values()):
                rows.append(row)

    validate_rows(rows)
    return rows


def validate_rows(rows: Iterable[dict[str, str]]) -> None:
    """依 data-dictionary.md 驗證研究資料。"""

    errors: list[str] = []
    seen_tasks: set[tuple[str, str]] = set()
    session_metadata: dict[str, tuple[str, str, str]] = {}

    for index, row in enumerate(rows, start=2):
        participant_id = row["participant_id"]
        task_id = row["task_id"]
        completion = row["completion"]

        if not PARTICIPANT_PATTERN.fullmatch(participant_id):
            errors.append(f"第 {index} 列：participant_id 必須使用 P01 這類去識別代碼。")

        try:
            date.fromisoformat(row["session_date"])
        except ValueError:
            errors.append(f"第 {index} 列：session_date 必須是 YYYY-MM-DD。")

        if not row["device"]:
            errors.append(f"第 {index} 列：device 不可空白。")
        if not row["font_scaling"]:
            errors.append(f"第 {index} 列：font_scaling 不可空白。")

        if task_id not in TASK_LABELS:
            errors.append(f"第 {index} 列：task_id 必須是 A、B、C 或 D。")

        task_key = (participant_id, task_id)
        if participant_id and task_id and task_key in seen_tasks:
            errors.append(f"第 {index} 列：{participant_id} 的任務 {task_id} 重複。")
        seen_tasks.add(task_key)

        metadata = (row["session_date"], row["device"], row["font_scaling"])
        existing_metadata = session_metadata.setdefault(participant_id, metadata)
        if participant_id and existing_metadata != metadata:
            errors.append(f"第 {index} 列：{participant_id} 的日期、裝置或字級設定不一致。")

        if completion not in COMPLETION_VALUES:
            errors.append(f"第 {index} 列：completion 必須是 completed 或 not_completed。")

        try:
            assistance_level = _parse_integer(row["assistance_level"], "assistance_level", index)
            if assistance_level not in {0, 1, 2, 3}:
                errors.append(f"第 {index} 列：assistance_level 必須是 0–3。")
            elif completion == "completed" and assistance_level == 3:
                errors.append(f"第 {index} 列：completed 不可搭配 assistance_level 3。")
            elif completion == "not_completed" and assistance_level != 3:
                errors.append(f"第 {index} 列：not_completed 必須搭配 assistance_level 3。")
        except DataValidationError as error:
            errors.append(str(error))

        try:
            duration = _parse_number(row["duration_seconds"], "duration_seconds", index)
            if duration is not None and duration < 0:
                errors.append(f"第 {index} 列：duration_seconds 不可小於 0。")
        except DataValidationError as error:
            errors.append(str(error))

        if row["first_gesture"] not in GESTURE_VALUES:
            errors.append(f"第 {index} 列：first_gesture 必須是 tap、hold、undetermined 或空白。")
        if task_id == "A" and row["first_gesture"] == "":
            errors.append(f"第 {index} 列：任務 A 必須記錄 first_gesture。")

        try:
            error_count = _parse_integer(row["error_count"], "error_count", index)
            if error_count is None or error_count < 0:
                errors.append(f"第 {index} 列：error_count 必須是 0 以上整數。")
        except DataValidationError as error:
            errors.append(str(error))

        try:
            ease_score = _parse_integer(row["ease_score"], "ease_score", index)
            if ease_score is not None and ease_score not in {1, 2, 3, 4, 5}:
                errors.append(f"第 {index} 列：ease_score 必須是 1–5 或空白。")
        except DataValidationError as error:
            errors.append(str(error))

        for field in ("listening_correct", "thinking_correct", "speaking_correct"):
            if row[field] not in RECOGNITION_VALUES:
                errors.append(f"第 {index} 列：{field} 必須是 yes、no、uncertain 或空白。")
            if task_id == "C" and row[field] == "":
                errors.append(f"第 {index} 列：任務 C 必須填寫 {field}。")

        if row["error_recovery"] not in RECOVERY_VALUES:
            errors.append(
                f"第 {index} 列：error_recovery 必須是 reconnected、returned_idle、"
                "not_completed 或空白。"
            )
        if task_id == "D" and row["error_recovery"] == "":
            errors.append(f"第 {index} 列：任務 D 必須填寫 error_recovery。")

        if row["critical_issue"] not in CRITICAL_VALUES:
            errors.append(f"第 {index} 列：critical_issue 必須是 yes 或 no。")

        for field in ("observation",):
            pii_type = _contains_obvious_pii(row[field])
            if pii_type:
                errors.append(f"第 {index} 列：{field} 疑似包含{pii_type}，請先去識別化。")

    if errors:
        raise DataValidationError("\n".join(errors))


def _count_fraction(count: int, total: int) -> str:
    return "—" if total == 0 else f"{count}/{total}"


def _format_median(values: list[float]) -> str:
    if not values:
        return "—"
    value = statistics.median(values)
    return f"{value:.1f} 秒"


def _format_mean(values: list[int]) -> str:
    if not values:
        return "—"
    return f"{statistics.mean(values):.1f}"


def build_summary(rows: list[dict[str, str]], source_name: str) -> str:
    """建立不包含自動洞察的 Markdown 描述性摘要。"""

    participants = sorted({row["participant_id"] for row in rows})
    tasks_for_participant = {
        participant_id: {row["task_id"] for row in rows if row["participant_id"] == participant_id}
        for participant_id in participants
    }
    complete_sessions = sum(
        1 for task_ids in tasks_for_participant.values() if task_ids == set(TASK_LABELS)
    )
    incomplete_sessions = len(participants) - complete_sessions

    if not participants:
        evidence_status = "尚無研究結論"
        evidence_note = "資料表目前只有欄位，尚未匯入任何真人場次。"
    elif complete_sessions < 5:
        evidence_status = "提前訊號，尚不足以收斂"
        evidence_note = "完整場次少於 5 場，只能用於發現問題，不能視為穩定偏好。"
    else:
        evidence_status = "第一輪質性證據"
        evidence_note = "可開始跨場次主題分析；仍不代表統計顯著或所有長輩。"

    lines = [
        "# Kinsun 長輩陪伴對話：可用性測試彙整",
        "",
        f"> 產生日期：{date.today().isoformat()}｜資料來源：`{source_name}`",
        f"> 證據狀態：**{evidence_status}**。{evidence_note}",
        "",
        "## 1. 研究狀態",
        "",
        f"- 去識別參與者：{len(participants)} 位",
        f"- 完整場次（A–D 皆有紀錄）：{complete_sessions} 場",
        f"- 不完整場次：{incomplete_sessions} 場",
        f"- 任務觀察列：{len(rows)} 列",
        "",
        "## 2. 任務結果",
        "",
        "| 任務 | 觀察數 | 完成 | 無協助完成 | 一次中性提示內完成 | 中位時間 | 平均難易度 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for task_id, task_label in TASK_LABELS.items():
        task_rows = [row for row in rows if row["task_id"] == task_id]
        total = len(task_rows)
        completed = sum(row["completion"] == "completed" for row in task_rows)
        unassisted = sum(
            row["completion"] == "completed" and row["assistance_level"] == "0" for row in task_rows
        )
        neutral_prompt = sum(
            row["completion"] == "completed" and row["assistance_level"] in {"0", "1"}
            for row in task_rows
        )
        durations = [
            float(row["duration_seconds"]) for row in task_rows if row["duration_seconds"] != ""
        ]
        ease_scores = [int(row["ease_score"]) for row in task_rows if row["ease_score"] != ""]
        lines.append(
            f"| {task_id} {task_label} | {total} | {_count_fraction(completed, total)} | "
            f"{_count_fraction(unassisted, total)} | {_count_fraction(neutral_prompt, total)} | "
            f"{_format_median(durations)} | {_format_mean(ease_scores)} |"
        )

    gesture_counts = Counter(
        row["first_gesture"] for row in rows if row["task_id"] == "A" and row["first_gesture"]
    )
    lines.extend(
        [
            "",
            "## 3. 任務 A 首選手勢",
            "",
            "| 首選手勢 | 次數 |",
            "| --- | ---: |",
            f"| 短按兩次 | {gesture_counts['tap']} |",
            f"| 按住放開 | {gesture_counts['hold']} |",
            f"| 無法判定 | {gesture_counts['undetermined']} |",
        ]
    )

    state_rows = [row for row in rows if row["task_id"] == "C"]
    lines.extend(
        [
            "",
            "## 4. 任務 C 狀態辨識",
            "",
            "| 狀態 | 正確 | 不正確 | 不確定 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for field, label in (
        ("listening_correct", "Listening"),
        ("thinking_correct", "Thinking"),
        ("speaking_correct", "Speaking"),
    ):
        counts = Counter(row[field] for row in state_rows)
        lines.append(f"| {label} | {counts['yes']} | {counts['no']} | {counts['uncertain']} |")

    recovery_counts = Counter(row["error_recovery"] for row in rows if row["task_id"] == "D")
    lines.extend(
        [
            "",
            "## 5. 任務 D 錯誤回復",
            "",
            "| 結果 | 次數 |",
            "| --- | ---: |",
            f"| 完成重新連線 | {recovery_counts['reconnected']} |",
            f"| 回到待機 | {recovery_counts['returned_idle']} |",
            f"| 未完成 | {recovery_counts['not_completed']} |",
        ]
    )

    critical_rows = [row for row in rows if row["critical_issue"] == "yes"]
    lines.extend(
        [
            "",
            "## 6. 需立即檢查的觀察",
            "",
        ]
    )
    if not critical_rows:
        lines.append("目前沒有標記為 `critical_issue=yes` 的資料列。")
    else:
        lines.extend(
            [
                "| 參與者代碼 | 任務 | 去識別化觀察 |",
                "| --- | --- | --- |",
            ]
        )
        for row in critical_rows:
            observation = row["observation"].replace("|", "｜") or "未填寫"
            lines.append(
                f"| {row['participant_id']} | {row['task_id']} {TASK_LABELS[row['task_id']]} | "
                f"{observation} |"
            )

    lines.extend(
        [
            "",
            "## 7. 研究者解讀與決策",
            "",
            "本節不由工具自動產生洞察。完成預定場次後，由研究者回看逐場觀察並補寫：",
            "",
            "- 跨 3 場以上重複出現的行為模式：待填。",
            "- 阻止核心任務的 P0／P1 問題：待填。",
            "- 雙手勢應保留、調整或增加教學的證據：待填。",
            "- 下一版修改與再次驗證範圍：待填。",
            "",
            "> 限制：本摘要是描述性質性研究彙整，不代表統計顯著、因果關係或所有長輩。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="驗證並彙整去識別化可用性測試 CSV。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="輸入 CSV 路徑")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="輸出 Markdown 路徑")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows = read_rows(args.input)
        summary = build_summary(rows, args.input.name)
    except DataValidationError as error:
        print(f"研究資料驗證失敗：\n{error}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as file:
        file.write(summary)
    print(f"完成：驗證 {len(rows)} 列，輸出 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
