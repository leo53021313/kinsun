from kinsun.binding.session import BindingState


def test_binding_state_values():
    assert BindingState.MENU.value == "menu"
    assert BindingState.AWAIT_CONFIRM.value == "confirm"
