from kinsun.accounts.models import Channel
from kinsun.binding.gate import AllowAllGate, ConsentGate


class _Resolver:
    def __init__(self, elder_id=None, boom=False):
        self._elder_id = elder_id
        self._boom = boom

    def consented_elder_id(self, channel, external_id):
        if self._boom:
            raise RuntimeError("db down")
        return self._elder_id


def test_gate_resolves_consented_elder():
    assert ConsentGate(_Resolver("e-1")).resolve_elder(Channel.LINE, "U-1") == "e-1"
    assert ConsentGate(_Resolver(None)).resolve_elder(Channel.LINE, "U-1") is None


def test_gate_returns_none_on_error():
    # 會話主鍵需要 elder_id 才能落記憶，解析故障無從放行 → 視同未綁定。
    assert ConsentGate(_Resolver("e-1", boom=True)).resolve_elder(Channel.LINE, "U-1") is None


def test_allow_all_gate_passes_line_id_through():
    gate = AllowAllGate()
    assert gate.resolve_elder(Channel.LINE, "U-1") == "U-1"
    assert gate.resolve_elder(Channel.APP, "") == ""
