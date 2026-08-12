from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tools" / "summarize_usability_results.py"
SPEC = importlib.util.spec_from_file_location("summarize_usability_results", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("無法載入可用性測試彙整工具")
SUMMARY_TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY_TOOL)


def valid_task_a_row(**overrides: str) -> dict[str, str]:
    row = {
        "participant_id": "P01",
        "session_date": "2026-07-27",
        "device": "iPhone 13",
        "font_scaling": "default",
        "task_id": "A",
        "completion": "completed",
        "assistance_level": "0",
        "duration_seconds": "8",
        "first_gesture": "tap",
        "error_count": "0",
        "ease_score": "5",
        "listening_correct": "",
        "thinking_correct": "",
        "speaking_correct": "",
        "error_recovery": "",
        "critical_issue": "no",
        "observation": "先看狀態文字，再按麥克風。",
    }
    row.update(overrides)
    return row


class SummarizeUsabilityResultsTests(unittest.TestCase):
    def write_csv(
        self,
        directory: Path,
        rows: list[dict[str, str]],
        fieldnames: tuple[str, ...] | list[str] | None = None,
    ) -> Path:
        path = directory / "sessions.csv"
        columns = list(fieldnames or SUMMARY_TOOL.REQUIRED_COLUMNS)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_empty_csv_generates_no_evidence_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            path = self.write_csv(Path(temp_directory), [])
            rows = SUMMARY_TOOL.read_rows(path)
            summary = SUMMARY_TOOL.build_summary(rows, path.name)

        self.assertEqual(rows, [])
        self.assertIn("尚無研究結論", summary)
        self.assertIn("去識別參與者：0 位", summary)

    def test_valid_rows_are_aggregated(self) -> None:
        rows = [
            valid_task_a_row(),
            valid_task_a_row(
                participant_id="P02",
                device="Pixel 8",
                first_gesture="hold",
                assistance_level="1",
                duration_seconds="12",
                ease_score="3",
            ),
            valid_task_a_row(
                task_id="C",
                first_gesture="",
                listening_correct="yes",
                thinking_correct="no",
                speaking_correct="uncertain",
                duration_seconds="15",
                ease_score="4",
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_directory:
            path = self.write_csv(Path(temp_directory), rows)
            validated_rows = SUMMARY_TOOL.read_rows(path)
            summary = SUMMARY_TOOL.build_summary(validated_rows, path.name)

        self.assertIn("去識別參與者：2 位", summary)
        self.assertIn("| 短按兩次 | 1 |", summary)
        self.assertIn("| 按住放開 | 1 |", summary)
        self.assertIn("| Listening | 1 | 0 | 0 |", summary)
        self.assertIn("| Thinking | 0 | 1 | 0 |", summary)

    def test_missing_columns_are_rejected(self) -> None:
        columns = [column for column in SUMMARY_TOOL.REQUIRED_COLUMNS if column != "observation"]
        with tempfile.TemporaryDirectory() as temp_directory:
            path = self.write_csv(Path(temp_directory), [], columns)
            with self.assertRaisesRegex(SUMMARY_TOOL.DataValidationError, "observation"):
                SUMMARY_TOOL.read_rows(path)

    def test_obvious_personal_data_is_rejected(self) -> None:
        for observation, expected in (
            ("請寄到 elder@example.com", "電子郵件"),
            ("受試者手機是 0912-345-678", "台灣手機號碼"),
        ):
            with self.subTest(observation=observation):
                with tempfile.TemporaryDirectory() as temp_directory:
                    path = self.write_csv(
                        Path(temp_directory),
                        [valid_task_a_row(observation=observation)],
                    )
                    with self.assertRaisesRegex(
                        SUMMARY_TOOL.DataValidationError,
                        expected,
                    ):
                        SUMMARY_TOOL.read_rows(path)


if __name__ == "__main__":
    unittest.main()
