"""LLM 介面與 Gemini 實作。系統指令＋多輪訊息 → 繁體國語漢字回應。"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """LLM 呼叫失敗。"""


@dataclass
class LLMUsage:
    """一段範圍內的 token 用量累計（可變累加器）。"""

    input_tokens: int = 0
    output_tokens: int = 0


# 用量收集器走 contextvars（✅ D-05 戊-2）：LLMClient 協定回傳純文字、不透出
# usage，改協定會波及所有替身與呼叫端；contextvars 讓 GeminiClient 申報用量、
# pipeline 收集，且各執行緒／請求的 context 彼此隔離，併發回合不會互相污染。
_usage_collector: contextvars.ContextVar[LLMUsage | None] = contextvars.ContextVar(
    "kinsun_llm_usage", default=None
)


@contextmanager
def collect_llm_usage(usage: LLMUsage) -> Iterator[None]:
    """在範圍內把 report_llm_usage 申報的用量累加進 usage。"""
    token = _usage_collector.set(usage)
    try:
        yield
    finally:
        _usage_collector.reset(token)


def report_llm_usage(input_tokens: int, output_tokens: int) -> None:
    """申報一次 LLM 呼叫的 token 用量；無收集器時靜默略過。"""
    usage = _usage_collector.get()
    if usage is None:
        return
    usage.input_tokens += input_tokens
    usage.output_tokens += output_tokens


def _report_usage_metadata(response) -> None:
    """從 Gemini 回應取 usage_metadata 申報；欄位缺漏（假替身／舊 SDK）就不申報。"""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return
    # 輸出＝候選＋思考：thinking 模型的思考 token 也計費為輸出。
    output = (getattr(meta, "candidates_token_count", 0) or 0) + (
        getattr(meta, "thoughts_token_count", 0) or 0
    )
    report_llm_usage(getattr(meta, "prompt_token_count", 0) or 0, output)


@dataclass(frozen=True)
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    # 模型回傳 function_call 時附帶的思考簽章；gemini-3 thinking 模型要求原封回帶。
    thought_signature: bytes | None = None


@dataclass(frozen=True)
class ToolResult:
    call: ToolCall
    output: str


@dataclass(frozen=True)
class ToolTurn:
    text: str | None
    tool_calls: list[ToolCall]


class LLMClient(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        response_schema: dict | None = None,
    ) -> str: ...
    def generate_tool_turn(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec],
        tool_results: list[ToolResult],
    ) -> ToolTurn: ...


def _to_contents(messages: list[Message]) -> list[dict]:
    role_map = {"user": "user", "assistant": "model"}
    return [
        {"role": role_map.get(m.role, "user"), "parts": [{"text": m.content}]} for m in messages
    ]


def _extract_tool_calls(response) -> list[ToolCall]:
    """逐一取出回應 parts 的 function_call，並保留同 part 的 thought_signature。

    需走 parts（而非 response.function_calls），因為 thought_signature 掛在 part 上，
    是 gemini-3 thinking 模型後續回帶工具結果時的必要欄位。
    """
    candidates = response.candidates or []
    if not candidates or candidates[0].content is None:
        return []
    calls: list[ToolCall] = []
    for part in candidates[0].content.parts or []:
        fc = part.function_call
        if fc is None:
            continue
        calls.append(
            ToolCall(
                name=fc.name,
                arguments=dict(fc.args or {}),
                thought_signature=part.thought_signature,
            )
        )
    return calls


class GeminiClient:
    def __init__(self, *, api_key: str, model: str, timeout: float, client_wrapper=None) -> None:
        if not api_key:
            raise LLMError("缺少 GEMINI_API_KEY")
        from google import genai
        from google.genai import types

        # 逾時掛在 client 上（2026-07-26 延遲實測）：先前 timeout 只存進欄位、從未
        # 傳給 SDK，等於 Gemini 呼叫沒有任何客戶端逾時——生產 llm_calls p95 11.5s、
        # max 23.8s，實測還撞過單輪 46 秒與 52 秒。ASR／TTS 的逾時之所以有效，
        # 差別就在有把值傳下去（兩者 latency 精準卡在 15s／30s）。
        # ⚠️ SDK 的 HttpOptions.timeout 單位是**毫秒**，設定檔（GEMINI_TIMEOUT_SECONDS）
        # 是秒，換算不可省——漏乘 1000 會變成 30 毫秒逾時，等於全部呼叫立刻失敗。
        # 掛在 client 而非逐次呼叫：本 client 的每個出口（generate／generate_tool_turn）
        # 都該受同一把逾時管，逐次傳容易漏掉新增的出口。
        client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout * 1000))
        )
        # client_wrapper 為觀測層的注入點（如 Opik track_genai）；None＝不包裝。
        # 保持 llm.py 不 import 觀測套件（依賴反轉），包裝由組裝層決定。
        self._client = client_wrapper(client) if client_wrapper is not None else client
        self._model = model
        self._timeout = timeout

    def generate(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        response_schema: dict | None = None,
    ) -> str:
        from google.genai import types

        config_kwargs: dict = {"system_instruction": system_prompt}
        if response_schema is not None:
            # 受控生成：模型被約束為合法 JSON，呼叫端可直接 json.loads（免撈殼）。用
            # response_json_schema（純 JSON schema dict），與工具的 parameters_json_schema
            # 同調，讓 app 層呼叫端只傳 dict、不 import google.genai（維持依賴反轉）。
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = response_schema
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=_to_contents(messages),
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:  # noqa: BLE001 - 統一轉成可辨識的 LLMError
            raise LLMError(f"Gemini 呼叫失敗：{exc}") from exc
        _report_usage_metadata(response)
        text = response.text
        if not text:
            raise LLMError("Gemini 回應為空")
        return text

    def generate_tool_turn(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec],
        tool_results: list[ToolResult],
    ) -> ToolTurn:
        from google.genai import types

        contents = _to_contents(messages)
        for tr in tool_results:
            # 回帶模型原始 function_call part（含 thought_signature）：gemini-3 thinking 模型
            # 要求 functionCall part 保留 thought_signature，缺了會 400 INVALID_ARGUMENT。
            contents.append(
                types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=tr.call.name, args=tr.call.arguments
                            ),
                            thought_signature=tr.call.thought_signature,
                        )
                    ],
                )
            )
            # ⚠️ role 必須是 `user`，不可用語意上更貼切的 `tool`（2026-07-26 實機驗證）：
            # `gemini-3.5-flash-lite`（.env 的正式模型）對 `role="tool"` 直接回 400
            # `Role 'tool' is not supported`，於是**每一輪用到工具的對話都失敗、退回
            # 「金孫剛剛沒聽清楚」**——天氣、衛教 RAG、新聞、排程、查證全中。完整往返實測：
            #   gemini-3.1-flash-lite：tool ✅ / user ✅
            #   gemini-3.5-flash-lite：tool ❌ 400 / user ✅
            # `user` 兩個模型都吃，故選它。由 test_llm 的
            # test_tool_results_go_back_with_a_role_gemini_accepts 守住。
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=tr.call.name, response={"result": tr.output}
                        )
                    ],
                )
            )
        genai_tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t.name, description=t.description, parameters_json_schema=t.parameters
                )
                for t in tools
            ]
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt, tools=[genai_tool]
                ),
            )
        except Exception as exc:  # noqa: BLE001 - 統一轉成可辨識的 LLMError
            raise LLMError(f"Gemini 工具呼叫失敗：{exc}") from exc
        _report_usage_metadata(response)
        tool_calls = _extract_tool_calls(response)
        if tool_calls:
            return ToolTurn(text=None, tool_calls=tool_calls)
        text = response.text
        if not text:
            raise LLMError("Gemini 回應為空")
        return ToolTurn(text=text, tool_calls=[])


def build_gemini_for(settings, model: str, *, client_wrapper=None) -> GeminiClient:
    """按用途建 Gemini client（✅ D-16 丁-5）：模型同主設定時呼叫端應直接共用主 client。"""
    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=model,
        timeout=settings.gemini_timeout_seconds,
        client_wrapper=client_wrapper,
    )
