"""對講機容量閘門（spec 2026-07-30 §10 B2）。

⚠️ 這**不是節流，是容量管理**。ASR 與 TTS 跑在同一顆 GPU 上，同時湧入的請求
不會併行而會排隊——結果是每個人都慢。限制併發並誠實告知排隊位置，等於
「少數人順暢」勝過「所有人都卡」。

⚠️ 名額**一定要在 finally 釋放**。漏放一次，那個名額就永久消失；漏放到滿，
所有人從此都在排隊，而伺服器看起來完全健康。
"""

import threading
import time

import pytest

from kinsun.channels.app.admission import AdmissionTimeout, TurnAdmission


def test_名額之內直接放行():
    gate = TurnAdmission(2)
    with gate.admit():
        assert gate.active() == 1
        with gate.admit():
            assert gate.active() == 2
    assert gate.active() == 0


def test_離開時釋放名額_例外也要釋放():
    gate = TurnAdmission(1)
    with pytest.raises(RuntimeError):
        with gate.admit():
            raise RuntimeError("這一輪炸了")
    # 沒有這一條保證的話，一次例外就永久少一個名額，滿了之後所有人從此排隊。
    assert gate.active() == 0
    with gate.admit():
        assert gate.active() == 1


def test_滿載時排隊_前面的做完就輪到():
    gate = TurnAdmission(1)
    order = []
    first_inside = threading.Event()
    release_first = threading.Event()

    def first():
        with gate.admit():
            order.append("first-in")
            first_inside.set()
            release_first.wait(2.0)
        order.append("first-out")

    def second():
        first_inside.wait(2.0)
        with gate.admit():
            order.append("second-in")

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    t2.start()
    first_inside.wait(2.0)
    time.sleep(0.05)
    assert order == ["first-in"], "第二個應該還在排隊"
    release_first.set()
    t1.join(2.0)
    t2.join(2.0)
    # 兩條背景執行緒若卡住不會拋錯、只會讓上面的 join 悄悄逾時——沒有這兩條，
    # 「執行緒沒跑完」跟「執行緒跑完但斷言剛好符合預期」在測試報告上長得一樣。
    assert not t1.is_alive()
    assert not t2.is_alive()
    assert order == ["first-in", "first-out", "second-in"]


def test_排隊時回報位置_使用者才知道要等多久():
    """靜默排隊與當機在畫面上長得一模一樣。長輩只會覺得金孫不理他。

    ⚠️ 這裡刻意不用固定 `time.sleep()` 後直接斷言「已經回報」：重載機器上
    `waiter` 執行緒可能還沒被排程到，50ms 內看不到回報不代表回報邏輯有錯，
    而是斷言下得太早——改成「等到回報出現、有上限」，避免這種假紅。
    """
    gate = TurnAdmission(1)
    positions = []
    inside = threading.Event()
    release = threading.Event()

    def holder():
        with gate.admit():
            inside.set()
            release.wait(2.0)

    def waiter():
        inside.wait(2.0)
        with gate.admit(on_queued=positions.append):
            pass

    t1 = threading.Thread(target=holder)
    t2 = threading.Thread(target=waiter)
    t1.start()
    t2.start()
    inside.wait(2.0)
    deadline = time.monotonic() + 2.0
    while not positions and time.monotonic() < deadline:
        time.sleep(0.01)
    assert positions == [1], "第一個排隊的人前面有 1 位"
    release.set()
    t1.join(2.0)
    t2.join(2.0)
    assert not t1.is_alive()
    assert not t2.is_alive()


def test_名額夠時不回報排隊_不要嚇沒有在等的人():
    gate = TurnAdmission(2)
    positions = []
    with gate.admit(on_queued=positions.append):
        pass
    assert positions == []


def test_等太久就放棄_不可讓人永遠掛在那裡():
    gate = TurnAdmission(1, queue_timeout=0.1)
    with gate.admit():
        with pytest.raises(AdmissionTimeout):
            with gate.admit():
                pass


def test_逾時放棄的人不佔排隊人數():
    """逾時卻沒把 waiting 減回去的話，後面的人看到的位置會越報越誇張。"""
    gate = TurnAdmission(1, queue_timeout=0.1)
    with gate.admit():
        with pytest.raises(AdmissionTimeout):
            with gate.admit():
                pass
        assert gate.waiting() == 0


def test_on_queued在鎖外呼叫_不會拖住其他呼叫端():
    """`on_queued` 若在鎖內呼叫，一個會阻塞的回呼（如 `ws.py` 的 `_Sender.send`
    最長等 5 秒）會讓同一時間所有人的 `active()`／`waiting()`／`admit()` 一起
    卡住。這裡模擬一個會阻塞的 `on_queued`，確認閘門的其他操作完全不受影響。

    ⚠️ 用一條「量測執行緒＋有上限的 join」而非直接呼叫：若鎖真的被卡住，
    直接呼叫會讓這條測試本身掛住（因為 `release_on_queued` 還沒被設），
    有上限的 join 才能把「卡住」本身變成可觀測、可斷言的失敗，而不是讓
    整個測試行程被吊死。
    """
    gate = TurnAdmission(1, queue_timeout=2.0)
    on_queued_started = threading.Event()
    release_on_queued = threading.Event()

    def blocking_on_queued(_position):
        on_queued_started.set()
        release_on_queued.wait(2.0)

    holder_inside = threading.Event()
    release_holder = threading.Event()

    def holder():
        with gate.admit():
            holder_inside.set()
            release_holder.wait(2.0)

    def waiter():
        with gate.admit(on_queued=blocking_on_queued):
            pass

    t_holder = threading.Thread(target=holder)
    t_holder.start()
    assert holder_inside.wait(2.0)

    t_waiter = threading.Thread(target=waiter)
    t_waiter.start()
    try:
        assert on_queued_started.wait(2.0), "on_queued 應該已經開始執行（並卡住）"

        result = {}

        def checker():
            result["active"] = gate.active()
            result["waiting"] = gate.waiting()

        checker_thread = threading.Thread(target=checker)
        checker_thread.start()
        checker_thread.join(0.5)
        assert not checker_thread.is_alive(), (
            "active()/waiting() 被 on_queued 卡住了，代表鎖沒有先放掉"
        )
        assert result == {"active": 1, "waiting": 1}
    finally:
        release_on_queued.set()
        release_holder.set()
        t_holder.join(2.0)
        t_waiter.join(2.0)

    assert not t_holder.is_alive()
    assert not t_waiter.is_alive()


def test_初始化時的參數驗證_不合理的設定要早死好過晚死():
    """`queue_timeout` 亂餵值不該安靜地變成別的意思：

    `None` 會讓 `wait_for` 永久等待（「等太久就放棄」這條保證整個失效卻不報錯）；
    `<=0` 會讓排隊形同不排隊（一進來就逾時，容量保護悄悄消失）。兩者都必須在
    建構當下就炸出來，好過留到畢典現場才被實測發現。
    """
    with pytest.raises(ValueError):
        TurnAdmission(0)
    with pytest.raises(ValueError):
        TurnAdmission(1, queue_timeout=0)
    with pytest.raises(ValueError):
        TurnAdmission(1, queue_timeout=-1)
    with pytest.raises(ValueError):
        TurnAdmission(1, queue_timeout=None)


def test_限制大於一時_峰值仍等於上限():
    """正式環境會用 limit>1；這條測試觀測到的 active() 峰值必須恰好等於上限，
    不多也不少——只在 limit=1 下測過的話，off-by-one 這種錯誤永遠測不到。

    N+1 位執行緒經同一個 threading.Barrier 幾乎同時衝進來（真重疊，不是依序
    跑完），逼出「至少有一位必須排隊」的情境；峰值用獨立的鎖記錄，讀寫時機
    完全落在 `with gate.admit():` 區塊內，因此峰值等同於 gate 實際核准的
    併發輪數。
    """
    limit = 3
    workers = limit + 1
    gate = TurnAdmission(limit, queue_timeout=2.0)
    lock = threading.Lock()
    state = {"current": 0, "peak": 0}
    barrier = threading.Barrier(workers)

    def worker():
        barrier.wait(2.0)
        with gate.admit():
            with lock:
                state["current"] += 1
                state["peak"] = max(state["peak"], state["current"])
            time.sleep(0.05)
            with lock:
                state["current"] -= 1

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(2.0)
    for t in threads:
        assert not t.is_alive()
    assert state["peak"] == limit


def test_先排隊的人先拿到_不會被插隊():
    """對每一位使用者的公平承諾：先按對講機的人不該因為晚到的人而被插到後面。

    先用 `go_event` 逐一控制五位排隊者「呼叫 `admit()`」的先後順序（藉此讓
    取號順序確定為 0..4），並用 `queued_event`（由 `on_queued` 回呼觸發）
    確認每一位都已經真的排進佇列、正卡在阻塞等待，才放行下一位——此時六條
    執行緒（一位持有者＋五位排隊者）同時活著、同時卡在各自的阻塞呼叫上，
    是真重疊而非依序執行。真正的併發只出現在「同時等待被放行」這一段：
    持有者釋放名額後，五位排隊者必須依照取號順序、逐一被放行。
    """
    gate = TurnAdmission(1, queue_timeout=2.0)
    order = []
    order_lock = threading.Lock()
    holder_inside = threading.Event()
    release_holder = threading.Event()

    def holder():
        with gate.admit():
            holder_inside.set()
            release_holder.wait(2.0)

    def waiter(index, go_event, queued_event):
        go_event.wait(2.0)
        with gate.admit(on_queued=lambda _pos: queued_event.set()):
            with order_lock:
                order.append(index)

    t_holder = threading.Thread(target=holder)
    t_holder.start()
    assert holder_inside.wait(2.0)

    go_events = [threading.Event() for _ in range(5)]
    queued_events = [threading.Event() for _ in range(5)]
    waiters = [
        threading.Thread(target=waiter, args=(i, go_events[i], queued_events[i])) for i in range(5)
    ]
    for w in waiters:
        w.start()

    # 依序放行、逐一確認「真的已經排進佇列」才放下一位：控制取號順序，
    # 但不因此犧牲真重疊——五位排隊者此刻都同時卡在真正的阻塞等待上。
    for go_event, queued_event in zip(go_events, queued_events, strict=True):
        go_event.set()
        assert queued_event.wait(2.0), "應該要真的排進佇列，而不是還沒排到"

    assert gate.waiting() == 5
    release_holder.set()
    t_holder.join(2.0)
    for w in waiters:
        w.join(2.0)
    assert not t_holder.is_alive()
    for w in waiters:
        assert not w.is_alive()
    assert order == [0, 1, 2, 3, 4], "先排隊的人被插隊了"


def _run_admission_race_trial() -> list[str]:
    """單次試驗：新來者是否搶在已排隊者之前拿到剛釋放的名額。

    抽成獨立函式而非迴圈內定義閉包（ruff B023：迴圈變數晚繫結，多執行緒場景下
    是真的會咬人的陷阱，不只是風格問題）；每次呼叫都是全新的區域變數，不共用
    任何跨試驗的狀態。
    """
    gate = TurnAdmission(1, queue_timeout=2.0)
    order: list[str] = []
    order_lock = threading.Lock()
    holder_inside = threading.Event()
    release_holder = threading.Event()
    waiter_queued = threading.Event()
    newcomer_ready = threading.Event()

    def holder():
        with gate.admit():
            holder_inside.set()
            release_holder.wait(2.0)

    def waiter():
        with gate.admit(on_queued=lambda _p: waiter_queued.set()):
            with order_lock:
                order.append("waiter")

    def newcomer():
        newcomer_ready.wait(2.0)
        with gate.admit():
            with order_lock:
                order.append("newcomer")

    t_holder = threading.Thread(target=holder)
    t_waiter = threading.Thread(target=waiter)
    t_newcomer = threading.Thread(target=newcomer)
    t_holder.start()
    assert holder_inside.wait(2.0)
    t_waiter.start()
    assert waiter_queued.wait(2.0)
    t_newcomer.start()
    # 讓新來者的嘗試與釋放盡量同時發生：起跑訊號一發，緊接著就釋放持有者，
    # 兩邊幾乎在同一時間搶鎖，藉此逼出真正的競速窗口。
    newcomer_ready.set()
    release_holder.set()

    t_holder.join(2.0)
    t_waiter.join(2.0)
    t_newcomer.join(2.0)
    assert not t_holder.is_alive()
    assert not t_waiter.is_alive()
    assert not t_newcomer.is_alive()
    return order


def test_新來的人在有空位但佇列非空時不可插隊():
    """名額釋放的瞬間若佇列裡還有人排著，新來的人不可以搶在他前面直接拿到名額——
    這正是快速通道「有空位就直接放行」必須同時檢查「佇列是空的」的理由；上一條
    測試（先排隊的人先拿到）測的是「已經在排隊的人之間」的順序，這裡測的是
    「還沒排過隊的新人」能不能繞過佇列硬插進來，是不同的失效模式。

    ⚠️ 這是一個真正的執行緒排程競速窗口：新來者與「剛被釋放、正要搶回鎖」的
    排隊者，兩者對同一把鎖的搶奪順序沒有保證，單次嘗試不足以驗證保護是否生效
    ——用重複試驗構成統計證據，只要有一次插隊就代表保護失效。實測數字：拿掉
    這道保護後 200 次裡有 83 次插隊；保留保護則 200 次全數 0 次插隊，且整體
    耗時不到 1 秒，不會拖慢測試套件。
    """
    trials = 200
    jumps = [
        (trial, order)
        for trial in range(trials)
        if (order := _run_admission_race_trial()) != ["waiter", "newcomer"]
    ]
    assert jumps == [], f"新來的人插隊了：{jumps[:5]}（共 {len(jumps)}/{trials} 次）"


def test_釋放後真正輪到號的人要被立即叫醒_不能只notify一位():
    """`notify()`（只叫醒一位）在取號設計下不會讓錯的人插隊（述詞已經擋住這件事，
    見上面兩條測試），但可能讓**對的人永遠沒被叫醒**——CPython 的 `Condition`
    挑的是牠自己內部等待佇列最前面那個，那個順序不保證等於我們自己的取號順序
    （尤其 `on_queued` 拿掉持鎖之後，不同排隊者真正呼叫 `wait_for` 的時間點可能
    跟取號順序顛倒）。若釋放時只叫醒一位、剛好叫醒的不是輪到號的那位，他發現
    不是自己會重新睡回去；但因為只叫醒一位，真正輪到號的那位可能完全沒被
    叫到——名額明明空著卻沒有人拿到，直到他自己的逾時。

    刻意讓 `front`（真正的隊伍最前面）卡在一個很慢的 `on_queued`，讓 `decoy`
    先一步真正進入 `wait_for`，逼出 CPython 內部喚醒順序與我們取號順序不一致
    的情境；`front` 的 `queue_timeout` 刻意設得夠長（1.0 秒），這樣「0.3 秒內
    有沒有被放行」才能真正反映「有沒有被明確叫醒」，而不是巧合撞上自己的
    逾時邊界（過短的逾時會讓兩邊剛好同時到期，製造假象——已用探測腳本
    驗證過這個陷阱：0.3 秒逾時時看似「還是通過」，其實是巧合）。
    """
    gate = TurnAdmission(1, queue_timeout=1.0)
    holder_inside = threading.Event()
    release_holder = threading.Event()
    front_registered = threading.Event()
    release_front_on_queued = threading.Event()
    decoy_waiting = threading.Event()
    result = {"granted_front": False, "timeout_front": False}

    def holder():
        with gate.admit():
            holder_inside.set()
            release_holder.wait(2.0)

    def slow_on_queued(_position):
        front_registered.set()
        release_front_on_queued.wait(2.0)

    def front():
        try:
            with gate.admit(on_queued=slow_on_queued):
                result["granted_front"] = True
        except AdmissionTimeout:
            result["timeout_front"] = True

    def decoy():
        assert front_registered.wait(2.0)

        def fast_on_queued(_position):
            decoy_waiting.set()

        try:
            with gate.admit(on_queued=fast_on_queued):
                pass
        except AdmissionTimeout:
            pass

    t_holder = threading.Thread(target=holder)
    t_holder.start()
    assert holder_inside.wait(2.0)

    t_front = threading.Thread(target=front)
    t_front.start()
    assert front_registered.wait(2.0)

    t_decoy = threading.Thread(target=decoy)
    t_decoy.start()
    assert decoy_waiting.wait(2.0)

    # 讓 decoy 真正先進入 wait_for（此刻 front 還卡在慢速 on_queued 裡），
    # 藉此讓 CPython 內部的喚醒順序與我們的取號順序刻意錯開。
    time.sleep(0.05)
    release_front_on_queued.set()
    time.sleep(0.05)

    release_holder.set()

    # 觀察窗：只等一小段時間（遠短於 1.0 秒的個別逾時），確認 front 是否已被
    # 放行。用 join(短逾時) 而非死等，才能把「卡住」本身變成可觀測、有上限的
    # 失敗，而不是讓這條測試自己被吊住一整秒。
    t_front.join(0.3)
    front_still_blocked = t_front.is_alive()

    # 收尾：不管上面看到什麼，都要讓所有背景執行緒真正結束才能離開這條測試，
    # 避免卡住的執行緒殘留到下一條測試。
    t_holder.join(2.0)
    t_front.join(2.0)
    t_decoy.join(2.0)
    assert not t_holder.is_alive()
    assert not t_front.is_alive()
    assert not t_decoy.is_alive()

    assert not front_still_blocked, (
        "真正輪到號的人在名額釋放後 0.3 秒內仍未被放行——"
        "notify() 只叫醒一位時，叫醒的可能不是輪到號的那位"
    )
