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


class _BindingResolver:
    def __init__(self, elder_id=None, boom=False):
        self._elder_id = elder_id
        self._boom = boom

    def bound_elder_id(self, channel, external_id):
        if self._boom:
            raise RuntimeError("db down")
        return self._elder_id


def test_allow_all_gate_resolves_bound_elder_id():
    """✅ D-19（丙-2）：旁路模式也解析 elder_id——切旗標不再換記憶主鍵。"""
    gate = AllowAllGate(_BindingResolver("e-1"))
    assert gate.resolve_elder(Channel.LINE, "U-1") == "e-1"


def test_allow_all_gate_falls_back_to_external_id_when_unbound():
    gate = AllowAllGate(_BindingResolver(None))
    assert gate.resolve_elder(Channel.LINE, "U-1") == "U-1"


def test_allow_all_gate_falls_back_on_resolver_error():
    gate = AllowAllGate(_BindingResolver("e-1", boom=True))
    assert gate.resolve_elder(Channel.LINE, "U-1") == "U-1"


def test_allow_all_gate_without_resolver_passes_through():
    gate = AllowAllGate()
    assert gate.resolve_elder(Channel.LINE, "U-1") == "U-1"
    assert gate.resolve_elder(Channel.APP, "") == ""
