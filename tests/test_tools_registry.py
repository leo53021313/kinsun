from kinsun.llm import ToolSpec
from kinsun.tools.registry import ToolInvocationContext, ToolRegistry

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


def test_dispatch_passes_optional_invocation_context():
    reg = ToolRegistry()
    seen = []

    def handler(args, context=None):
        seen.append(context)
        return "ok"

    context = ToolInvocationContext(trace_id="trace-1", elder_id="elder-1", has_risk_signal=True)
    reg.register(SPEC, handler)

    assert reg.dispatch("echo", {}, context=context) == "ok"
    assert seen == [context]


def test_dispatch_unchanged_when_tracing_disabled():
    # 工程觀測停用（預設）時，dispatch 行為與加裝飾器前一致。
    from kinsun.tracing import client as tracing_client

    tracing_client.reset_for_test()
    reg = ToolRegistry()
    reg.register(SPEC, lambda args: f"echo:{args.get('x')}")
    assert reg.dispatch("echo", {"x": 7}) == "echo:7"
