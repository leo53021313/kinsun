"""背景落庫的行為：預設同步、啟用後不阻塞、過載丟棄、關閉時排空。"""

from __future__ import annotations

import threading
import time

import pytest

from kinsun import background


@pytest.fixture(autouse=True)
def _reset():
    """每個測試都從「未設定＝同步」的狀態開始，並確保不把池留給下一個測試。"""
    background.reset_for_test()
    yield
    background.reset_for_test()


def test_defaults_to_running_inline():
    """未 configure＝當場執行：單元測試與 CLI 不必知道背景池存在。"""
    ran_in: list[str] = []

    background.run(lambda: ran_in.append(threading.current_thread().name))

    assert ran_in == [threading.current_thread().name]


def test_configured_writer_runs_off_the_calling_thread():
    background.configure(max_workers=2)
    ran_in: list[str] = []
    done = threading.Event()

    def action() -> None:
        ran_in.append(threading.current_thread().name)
        done.set()

    background.run(action)

    assert done.wait(timeout=5), "背景動作未在時限內執行"
    assert ran_in[0] != threading.current_thread().name


def test_caller_is_not_blocked_by_a_slow_action():
    """本功能的重點：慢寫入不可以拖住呼叫端（＝長輩的回覆）。"""
    background.configure(max_workers=1)
    released = threading.Event()

    background.run(released.wait)  # 一直卡著，直到測試放行

    started = time.monotonic()
    background.run(lambda: None)
    elapsed = time.monotonic() - started

    released.set()
    assert elapsed < 0.5, f"提交動作本身耗時 {elapsed:.2f}s，呼叫端被拖住了"


def test_failures_are_swallowed_and_logged(caplog):
    """落庫失敗絕不可以冒到主流程——它跑在別的執行緒，例外必須就地吞掉。"""
    background.configure(max_workers=1)

    background.run(lambda: 1 / 0)
    background.shutdown()

    assert "背景落庫失敗" in caplog.text


def test_shutdown_drains_pending_actions():
    """關閉時要把已排隊的寫入寫完，否則部署重啟就會吃掉最後幾筆觀測。"""
    background.configure(max_workers=1)
    done: list[int] = []

    for i in range(5):
        background.run(lambda i=i: done.append(i))
    background.shutdown()

    assert sorted(done) == [0, 1, 2, 3, 4]


def test_overflow_is_dropped_with_a_warning_instead_of_growing_without_bound(caplog):
    """佇列有上限：資料庫變慢時寧可丟掉觀測並留警告，也不要把記憶體吃光。

    這些寫入本來就是 best-effort（safe_record 一向吞掉錯誤），過載時丟棄與
    「寫失敗」對呼叫端是同一件事；但無上限的佇列會在 Supabase 慢下來時把
    行程撐爆——那會連帶弄死長輩的對話，比少幾筆稽核嚴重得多。
    """
    background.configure(max_workers=1, max_pending=2)
    released = threading.Event()
    background.run(released.wait)  # 佔住唯一的 worker

    for _ in range(20):
        background.run(lambda: None)

    released.set()
    background.shutdown()
    assert "背景落庫佇列已滿" in caplog.text


def test_reconfigure_replaces_the_previous_writer():
    """重複 configure 不可以留下孤兒執行緒池（reload 開發模式會走到）。"""
    background.configure(max_workers=1)
    first = background._writer
    background.configure(max_workers=2)

    assert background._writer is not first
    assert first is not None and first.is_closed


# ── 完成訊號（2026-07-30 審查 H2）─────────────────────────────────────
#
# 多數呼叫端不理 handle（觀測稽核沒有人在等）。少數呼叫端有一條「後續步驟真的會讀
# 這筆寫入」的路徑，需要在交出回應前收斂——見 `agent._record_turn_background`。


def test_inline_mode_returns_an_already_done_handle():
    """同步模式：run() 回來時就已經做完了，wait 不可以真的等。"""
    handle = background.run(lambda: None)
    assert handle.wait(0.0)


def test_handle_becomes_done_after_the_background_action_finishes():
    background.configure(max_workers=1)
    released = threading.Event()

    handle = background.run(released.wait)

    assert not handle.wait(0.05), "動作還沒做完，handle 不該是 done"
    released.set()
    assert handle.wait(5), "動作做完後 handle 應轉為 done"


def test_handle_becomes_done_even_when_the_action_raises():
    """失敗也算「這筆已經處理完」——呼叫端等的是「不會再變了」，不是「成功了」。"""
    background.configure(max_workers=1)

    def boom() -> None:
        raise RuntimeError("boom")

    handle = background.run(boom)

    assert handle.wait(5)


def test_handle_never_completes_when_the_queue_is_full(caplog):
    """佇列滿＝整筆被丟棄，handle 永遠不會 done——這正是呼叫端該看到的事實。

    刻意不在丟棄時把 handle 標記完成：那會讓「寫入被丟掉」偽裝成「寫入完成」，
    而 B2 之後被丟掉的是**長輩的對話記憶**，不再只是稽核。
    """
    background.configure(max_workers=1, max_pending=1)
    released = threading.Event()
    background.run(released.wait)  # 佔住唯一的 worker
    background.run(lambda: None)  # 填滿佇列

    dropped = background.run(lambda: None)

    assert not dropped.wait(0.05)
    released.set()
    background.shutdown()
    assert "背景落庫佇列已滿" in caplog.text
