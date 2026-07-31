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
    assert order == ["first-in", "first-out", "second-in"]


def test_排隊時回報位置_使用者才知道要等多久():
    """靜默排隊與當機在畫面上長得一模一樣。長輩只會覺得金孫不理他。"""
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
    time.sleep(0.05)
    assert positions == [1], "第一個排隊的人前面有 1 位"
    release.set()
    t1.join(2.0)
    t2.join(2.0)


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
