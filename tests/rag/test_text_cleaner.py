"""衛教文字清理：全形空白、連續空白、多重空行、首尾修剪。"""

from __future__ import annotations

from kinsun.rag.text_cleaner import clean_text


def test_fullwidth_space_becomes_halfwidth():
    assert clean_text("量　血壓") == "量 血壓"


def test_collapses_runs_of_spaces_and_tabs():
    assert clean_text("規律  量\t\t血壓") == "規律 量 血壓"


def test_strips_each_line_and_collapses_blank_lines():
    text = "第一段  \n\n\n\n第二段"
    assert clean_text(text) == "第一段\n\n第二段"


def test_strips_leading_and_trailing_whitespace():
    assert clean_text("\n  高血壓衛教  \n") == "高血壓衛教"


def test_empty_input_stays_empty():
    assert clean_text("") == ""
