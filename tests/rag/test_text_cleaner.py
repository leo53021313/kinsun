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


def test_strips_nul_bytes():
    """Postgres text 欄位不接受 NUL（0x00），清理時一併移除。"""
    assert clean_text("高血壓\x00衛教") == "高血壓衛教"


def test_strips_view_counter_lines():
    """點閱計數行每次請求都在變，會讓同一頁的內容雜湊永遠不同、每輪重嵌
    （2026-07-27 實測 hpa Detail 頁兩次抓取唯一差異＝點閱次數 +1）；對檢索也毫無價值。"""
    text = "高血壓衛教重點\n點閱次數：166556\n規律量血壓"
    assert clean_text(text) == "高血壓衛教重點\n規律量血壓"
    assert clean_text("瀏覽人次: 1,234") == ""
    assert clean_text("觀看次數：42") == ""
    # 內文提及次數的完整句子不可誤殺
    assert clean_text("這支影片的點閱次數：破百萬，很受長輩歡迎") == "這支影片的點閱次數：破百萬，很受長輩歡迎"
