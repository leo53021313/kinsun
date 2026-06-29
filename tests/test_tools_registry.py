from kinsun.llm import ToolSpec
from kinsun.tools.registry import ToolRegistry

SPEC = ToolSpec(
    name="echo", description="回傳輸入", parameters={"type": "object", "properties": {}}
)


def test_register_and_specs():
    reg = ToolRegistry()
    reg.register(SPEC, lambda args: "ok")
    assert reg.specs() == [SPEC]


def test_dispatch_calls_handler():
    reg = ToolRegistry()
    reg.register(SPEC, lambda args: f"got {args.get('x')}")
    assert reg.dispatch("echo", {"x": 1}) == "got 1"


def test_dispatch_unknown_tool_returns_friendly():
    assert "找不到工具" in ToolRegistry().dispatch("nope", {})


def test_dispatch_handler_exception_returns_friendly():
    reg = ToolRegistry()

    def boom(args):
        raise RuntimeError("boom")

    reg.register(SPEC, boom)
    assert "工具執行失敗" in reg.dispatch("echo", {})  # 不拋
