"""日誌設定單一入口：兩個常駐行程共用，且重複呼叫安全。

⚠️ 本模組的測試會動到 root logger，故每則都以 fixture 完整還原——否則會污染
其他測試的 caplog。
"""

from __future__ import annotations

import io
import logging

import pytest

from kinsun import logging_setup


@pytest.fixture(autouse=True)
def _restore_root():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    noisy = {name: logging.getLogger(name).level for name in logging_setup.NOISY_LOGGERS}
    logging_setup.reset_for_test()
    try:
        yield
    finally:
        logging_setup.reset_for_test()
        root.handlers[:] = handlers
        root.setLevel(level)
        for name, lvl in noisy.items():
            logging.getLogger(name).setLevel(lvl)


def _capture() -> io.StringIO:
    stream = io.StringIO()
    logging_setup.setup_logging(stream=stream)
    return stream


def test_kinsun_info_reaches_the_stream():
    """設定前 root 停在預設的 WARNING，kinsun.* 的 INFO 一行都不會出現。"""
    stream = _capture()
    logging.getLogger("kinsun.proactive").info("問候已送出 elder=%s", "e1")
    assert "問候已送出 elder=e1" in stream.getvalue()


def test_line_carries_a_timestamp_and_the_logger_name():
    """「何時開始壞的」與「誰印的」是查故障的兩個起點，缺一不可。"""
    stream = _capture()
    logging.getLogger("kinsun.scheduler").warning("job 失敗")
    line = stream.getvalue().strip()
    assert "kinsun.scheduler" in line
    assert "WARNING" in line
    assert line[:4].isdigit()  # 開頭是年份（asctime）


def test_calling_twice_does_not_duplicate_output():
    """--reload 與測試會重複呼叫；重複掛 handler 會讓每一行印兩次。"""
    stream = _capture()
    logging_setup.setup_logging(stream=io.StringIO())  # 第二次應整段跳過
    logging.getLogger("kinsun.web").info("只該出現一次")
    assert stream.getvalue().count("只該出現一次") == 1


def test_noisy_third_party_loggers_are_quieted():
    """Opik 每 10 秒探測一次存活，httpx 就印一行——實測佔排程日誌 24%。"""
    stream = _capture()
    logging.getLogger("httpx").info("HTTP Request: GET /api/is-alive/ping")
    assert stream.getvalue() == ""


def test_quieted_loggers_still_report_real_problems():
    """壓的是噪音不是訊號：第三方真的出事仍要看得到。"""
    stream = _capture()
    logging.getLogger("httpx").warning("connection reset")
    assert "connection reset" in stream.getvalue()


def test_level_is_configurable_without_an_env_key():
    stream = io.StringIO()
    logging_setup.setup_logging(level=logging.WARNING, stream=stream)
    logging.getLogger("kinsun.web").info("看不到")
    logging.getLogger("kinsun.web").warning("看得到")
    assert "看不到" not in stream.getvalue()
    assert "看得到" in stream.getvalue()
