from kinsun import tracing
from kinsun.tracing import client as tracing_client


def test_wrap_genai_is_identity_when_disabled():
    tracing_client.reset_for_test()
    sentinel = object()
    assert tracing.wrap_genai(sentinel) is sentinel
