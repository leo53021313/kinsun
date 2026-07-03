from kinsun.binding.gate import AllowAllGate, ConsentGate


class _Checker:
    def __init__(self, result=True, boom=False):
        self._result = result
        self._boom = boom

    def is_consented_elder(self, line_user_id):
        if self._boom:
            raise RuntimeError("db down")
        return self._result


def test_gate_delegates_to_checker():
    assert ConsentGate(_Checker(True)).allows("U-1") is True
    assert ConsentGate(_Checker(False)).allows("U-1") is False


def test_gate_fail_open_on_error():
    assert ConsentGate(_Checker(boom=True)).allows("U-1") is True


def test_allow_all_gate_always_allows():
    gate = AllowAllGate()
    assert gate.allows("U-1") is True
    assert gate.allows("") is True
