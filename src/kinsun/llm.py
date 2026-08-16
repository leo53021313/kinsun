"""LLM 介面與 Gemini 實作。系統指令＋多輪訊息 → 繁體國語漢字回應。"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from kinsun import turn_context


class LLMError(Exception):
    """LLM 呼叫失敗。"""


# 工具回合的思考層級。**不可省略**——省略掉的預設值在 `gemini-3.5-flash-lite` 上等於
# 「工具形同不存在」（2026-07-27 Opik 對照＋原封重放實測）。
#
# 這是 3.1→3.5 平移升版（2026-07-25）的第二顆地雷，第一顆是 `role="tool"` 回 400。
# 症狀比 400 陰險：不報錯，模型改成**用講的代替查**——長輩問「哪一家拉麵店」，它回
# 「系統這裡查不太到名字」（`web_search` 根本沒動），或直接編一個店名出來
# （實測編過一蘭、山頭火、一番）。
#
# 生產數據（Opik project `kinsun`，帶工具的呼叫中真的吐出 function_call 的比例）：
#   07-20/21 gemini-3.1-flash-lite：21/62   07-26/27 gemini-3.5-flash-lite：4/24
#   07-27 App 對話（7 輪、多次該查）：0/7
# 拿 07-27 那筆 24 輪真實請求原封重放，一次只換一個變因：
#   不設（現況）3/10、LOW 2/7、**MEDIUM 5/5**、HIGH 5/5；換回 3.1 不設 3/3。
#   工具數不是變因——3.5 縮回舊的 5 個工具仍是 0/3。
# 延遲代價（同一筆請求中位數）：不設 ~1.0s、MEDIUM 2.33s、HIGH 2.8–3.5s。
#
# 選 MEDIUM 而非 HIGH：兩者工具呼叫率同為 5/5，HIGH 多花約 1 秒買不到東西——而這一秒
# 直接加在長輩的等待上（端到端 07-26 實測 9.22s）。⚠️ 不要為了省延遲降到 LOW，實測
# LOW 與「不設」同樣不可靠。
#
# 只掛在工具回合：`generate()`（危急分級、濫用審核、摘要、反思）走受控生成、不需要
# 選工具，那條路上的每一毫秒都是長輩的等待。
TOOL_TURN_THINKING_LEVEL = "MEDIUM"


# 「這個錯誤重試有機會成功嗎？」的單一判準。
#
# ⚠️ 為什麼是字串比對而不是型別／狀態碼（2026-07-27）：同一個配額錯誤會以三種形狀出現
# ——`google.genai.errors.APIError`（我們自己的呼叫）、mem0 內部包裝過的例外
# （長期記憶寫入，實測 scheduler.log 的 15 筆 429 全走這條）、以及本模組翻譯出的
# `LLMError`。呼叫端拿到的是哪一種取決於它站在哪一層，型別比對會在跨層時漏掉。
#
# ⚠️ 白名單而非黑名單：認不出來的一律**不**重試。這個預設值必須偏保守——排程端的
# 重試會拉長夜間批次，而多數程式錯誤重試幾次都一樣。
#
# 清單原本住在 `rag/embeddings.py`，2026-07-27 搬來這裡供 cron 端共用——同一個判斷
# 散成兩份，遲早會有一份忘了更新。
_RETRYABLE_MARKERS = (
    "429",
    "rate limit",
    "too many requests",
    "resource_exhausted",
    "quota",
    "temporarily unavailable",
    "503",
    "timed out",
    "timeout",
    "readtimeout",
    "connecttimeout",
)


def is_retryable_llm_error(exc: BaseException) -> bool:
    """配額、限流、暫時性故障→True；其餘→False。"""
    message = str(exc).lower()
    return any(marker in message for marker in _RETRYABLE_MARKERS)


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
        response_schema: dict | None = None,
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

    def _budgeted_http_options(self):
        """這一次呼叫該用多久的逾時：`None`＝沒開預算，沿用掛在 client 上的那把。

        ⚠️ 逐次逾時管得住**一次**呼叫，管不住三次相加（2026-07-28 實錄）：Gemini 3.5
        過載那晚，一輪裡的分級／審核／生成各自卡滿 30 秒才放棄，長輩等了 96.6 秒才
        聽到回退話術。故本輪剩餘時間比逐次逾時短時，以剩餘時間為準。

        預算只會把逾時**縮短**不會放寬——`min` 不可寫成 `max`：那會讓一輪的預算變成
        單次呼叫的**下限**，比沒有這個功能更糟。

        預算已用完就直接拋，連打都不要打出去：那通呼叫的答案不管多好都來不及給長輩
        聽，而它還會佔著配額與連線。拋 `LLMError` 是刻意的——三個呼叫端
        （分級器 fail-safe 留痕、審核器 fail-open 放行、生成端回退話術）早就各自備好
        了 LLM 故障的降級路徑，走同一條即可，不必為預算另闢分支。
        """
        from google.genai import types

        remaining = turn_context.remaining_budget()
        if remaining is None:
            return None
        if remaining <= 0:
            raise LLMError(f"本輪時間已用完（超支 {-remaining:.1f} 秒），不再呼叫 Gemini")
        return types.HttpOptions(timeout=int(min(self._timeout, remaining) * 1000))

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
        http_options = self._budgeted_http_options()
        if http_options is not None:
            config_kwargs["http_options"] = http_options
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
        response_schema: dict | None = None,
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
        config_kwargs: dict = {
            "system_instruction": system_prompt,
            "tools": [genai_tool],
            "thinking_config": types.ThinkingConfig(thinking_level=TOOL_TURN_THINKING_LEVEL),
        }
        # 工具與結構化輸出可以並用（2026-08-16 實機驗證 gemini-3.5-flash-lite）：要叫
        # 工具的那幾輪照樣回 function_call、`text` 為空；產生最終回覆的那一輪才回 JSON。
        # ⚠️ 呼叫端仍要能吃「不是 JSON」的回覆——schema 是請求，不是保證。
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = response_schema
        http_options = self._budgeted_http_options()
        if http_options is not None:
            config_kwargs["http_options"] = http_options
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
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
