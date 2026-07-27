from kinsun.llm import ToolSpec
from kinsun.tools.registry import (
    TOOL_OUTPUT_MAX_CHARS,
    ToolInvocationContext,
    ToolRegistry,
)


def _spec(name: str) -> ToolSpec:
    return ToolSpec(name=name, description="", parameters={"type": "object", "properties": {}})


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


# ── 工具邊界防護（2026-07-27）──
#
# 缺陷是實測出來的，不是推測：模型送 weekday="3"（字串）時，Python 的
# `'<=' not supported between instances of 'int' and 'str'` 這句英文原文會被包進工具
# 回傳字串、餵回模型 context——最壞的情況是金孫照著唸給長輩聽。
# 同型：news 的 `.strip()` 對 list 拋 AttributeError，被 dispatch 的 bare except 吞成
# 一句「請稍後再試」，而「請稍後再試」正是在教模型用同樣的參數再打一次。


def test_dispatch_reports_the_exception_type_not_its_message():
    """例外**類型**對排查有用；**訊息**可能是英文原文或含敏感內容，不可外流。"""
    registry = ToolRegistry()
    registry.register(_spec("boom"), lambda args: (_ for _ in ()).throw(ValueError("內部細節 abc")))
    reply = registry.dispatch("boom", {})
    assert "ValueError" in reply
    assert "內部細節" not in reply


def test_dispatch_tells_the_model_not_to_retry_with_the_same_arguments():
    """原文案「請稍後再試」等於在教模型原封重打；工具迴圈沒有重複偵測，會白燒一輪。"""
    registry = ToolRegistry()
    registry.register(_spec("boom"), lambda args: (_ for _ in ()).throw(RuntimeError("x")))
    assert "再試一次" not in registry.dispatch("boom", {}).replace("不要用同樣參數再試一次", "")


def test_dispatch_rejects_non_dict_arguments_without_calling_the_handler():
    """模型偶爾會把參數送成字串或清單；讓 handler 自己去炸只會得到看不懂的例外。"""
    called = []
    registry = ToolRegistry()
    registry.register(_spec("spy"), lambda args: called.append(args) or "ok")
    reply = registry.dispatch("spy", "不是 dict")  # type: ignore[arg-type]
    assert called == []
    assert "參數" in reply


def test_dispatch_truncates_a_runaway_tool_output():
    """工具回傳整份文件時，會把模型的 context 灌爆並拖慢整輪。"""
    registry = ToolRegistry()
    registry.register(_spec("flood"), lambda args: "字" * 5000)
    assert len(registry.dispatch("flood", {})) <= TOOL_OUTPUT_MAX_CHARS + 40
