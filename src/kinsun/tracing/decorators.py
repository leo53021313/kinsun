"""track 裝飾器與 trace 標記；停用時全部 no-op。"""

from __future__ import annotations

import functools
import logging

from kinsun.tracing.client import is_enabled

logger = logging.getLogger("kinsun.tracing")


def track(
    name=None, type="general", capture_input=True, capture_output=True, ignore_arguments=None
):
    """為函式加 Opik span。開關判斷延後到呼叫時（裝飾器在 import 期套用，早於 configure）。

    停用＝直接跑原函式；啟用＝首次呼叫時才 lazy 包成 opik.track 並快取。

    `ignore_arguments`＝開著輸入捕捉、但排除指定參數（2026-07-27）。

    ⚠️ 為什麼需要它：opik 的 `extract_inputs` 只會自動 pop 掉 `self`／`cls`，
    **不認得金鑰**——實測 `extract_inputs(f, ("HTTP", "SECRET", "天氣"), {})` 原樣回傳
    `api_key`。沒有這個轉出，`tools/web_search.py` 那種「第二個參數是 api_key」的函式
    就只能整個關掉輸入，於是連長輩查了什麼都看不到。同理用於排除音檔 bytes
    （`asr`／`care_turn_voice`／`audio_upload` 的 `audio` 參數）。

    ⚠️ 附帶更正一個曾被寫進註解的錯誤前提：先前多處以「首參是 self」為由關閉輸入捕捉，
    但 opik 本來就會把 self 拿掉（`opik/decorator/inspect_helpers.py::extract_inputs`
    的 `arg_dict.pop("self")`）。那不是關閉輸入的正當理由，真正的理由只有金鑰、
    大型 bytes 與「參數是 store／callable 物件、序列化出來看不懂」三種。
    """

    def decorator(func):
        opik_wrapped = None

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal opik_wrapped
            if not is_enabled():
                return func(*args, **kwargs)
            if opik_wrapped is None:
                from opik import track as opik_track

                opik_wrapped = opik_track(
                    name=name,
                    type=type,
                    capture_input=capture_input,
                    capture_output=capture_output,
                    ignore_arguments=ignore_arguments,
                )(func)
            return opik_wrapped(*args, **kwargs)

        return wrapper

    return decorator


def tag_current_trace(*, trace_id="", channel="", elder_id="", **extra) -> None:
    """把 kinsun 的 trace_id 掛到當前 Opik trace（metadata + tags + thread），供 UI 關聯與搜尋。

    - elder_id 非空時設為 thread_id：同一長輩的多回合在 Opik 串成一條對話串（E1）。
    - **extra 追加任意 metadata（如 model、tier）。
    觀測失敗不可中斷對話：任何例外都吞掉並記 warning。停用時 no-op。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        metadata = {"kinsun_trace_id": trace_id, "elder_id": elder_id, **extra}
        kwargs = {"metadata": metadata, "tags": [t for t in (channel,) if t]}
        if elder_id:
            kwargs["thread_id"] = elder_id
        opik_context.update_current_trace(**kwargs)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik trace 標記失敗 trace=%s", trace_id)


def update_trace_metadata(**fields) -> None:
    """對當前 trace 追加 metadata（如風險 tier、是否走 fallback）；停用/失敗 no-op。

    用於 root 之後才算出的欄位——root 埋點時 tier/fallback 尚未知。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        opik_context.update_current_trace(metadata=fields)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik trace metadata 更新失敗")


def log_feedback_score(name, value, *, reason="") -> None:
    """對當前 trace 掛回饋分數（家屬/長輩評分、線上評測規則）；停用/失敗 no-op。"""
    if not is_enabled():
        return
    try:
        from opik import opik_context

        opik_context.update_current_trace(
            feedback_scores=[{"name": name, "value": value, "reason": reason}]
        )
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik feedback 掛載失敗 name=%s", name)


def set_current_trace_io(*, user_input: str = "", assistant_output: str = "") -> None:
    """把該輪的長輩原話與金孫回覆寫進當前 trace 的 input/output，讓 Opik Threads
    視圖顯示實際對話（First／Last message）；停用/失敗 no-op。

    刻意獨立於 @track 的 capture_input/output——那會連 audio bytes 與內部物件一起吞；
    這裡只寫乾淨文字。空字串者略過（如靜音誤觸沒有可顯示的原話）。update_current_trace
    對 input/output 是合併寫入、對 None 略過，故與既有的 metadata/thread 標記互不覆蓋。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        payload: dict = {}
        if user_input:
            payload["input"] = {"text": user_input}
        if assistant_output:
            payload["output"] = {"text": assistant_output}
        if payload:
            opik_context.update_current_trace(**payload)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik trace I/O 寫入失敗")


def rename_current_span(name: str) -> None:
    """把當前 span 改名；停用/失敗/空名一律 no-op。

    ⚠️ 為什麼需要它（2026-08-08 觀測盤點）：`@track` 的 `name` 在**裝飾時**就綁死，
    而有些 span 的身分要到執行期才知道——最典型的是 `tools/registry.py::dispatch`，
    它是所有工具共用的單一入口，於是 Opik 上每一個工具都叫 `dispatch`，看不出長輩
    問的是天氣還是行程。一輪裡叫了兩個工具時，兩個一樣的名字連「誰慢」都分不出來。

    只改名、不碰 input/output：那兩者已由 `@track` 的捕捉或 `set_current_span_io`
    負責，混在一起會讓覆寫規則變得難以預期。
    """
    if not is_enabled() or not name:
        return
    try:
        from opik import opik_context

        opik_context.update_current_span(name=name)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik span 改名失敗 name=%s", name)


def set_current_span_io(*, span_input=None, span_output=None) -> None:
    """把乾淨內容寫進當前 span（非 trace）的 input/output；停用/失敗 no-op。

    用於巢狀在 root 下的子流程（記憶寫入／每日摘要／每晚反思）——這些函式的參數多為
    store/client 物件（含 self），不能用 @track 的 capture_input/output（會吞內部物件、
    甚至 api_key／連線池），故在算出乾淨文字的點明確寫入本層 span。None 者略過。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        payload: dict = {}
        if span_input is not None:
            payload["input"] = span_input
        if span_output is not None:
            payload["output"] = span_output
        if payload:
            opik_context.update_current_span(**payload)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik span I/O 寫入失敗")


def current_opik_trace_id() -> str:
    """取當前 Opik trace 的 id，供 observability 存下、後台組深連結。

    停用／不在 trace context／失敗一律回空字串（呼叫端據此判斷是否有連結可掛）。
    必須在 @track 函式內呼叫才取得到——與 tag_current_trace 同一時機（對話進行中）。
    """
    if not is_enabled():
        return ""
    try:
        from opik import opik_context

        data = opik_context.get_current_trace_data()
        return data.id if data is not None else ""
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("取當前 Opik trace id 失敗")
        return ""


_prompt_cache: dict[str, tuple[str, object]] = {}


def attach_prompt(name: str, content: str) -> None:
    """把程式碼裡的 prompt 註冊進 Opik Prompt library（版本化）並連結到當前 trace。

    程式碼為真相（方案 A）：`content` 由呼叫端傳入的程式常數；Opik 只反映與關聯，
    不回頭影響執行——同名同內容不出新版，內容變才建新版，於是可跟線上評測分數對照
    「哪一版 prompt 品質較好」。停用／失敗一律 no-op，絕不中斷對話。

    首次（或內容變更）才碰後端建版，之後以行程內快取重用、每輪只做輕量的 trace 連結。
    `validate_placeholders=False`：本專案 prompt 用 Python `{var}`／純文字、非 mustache，
    且格式化在程式碼端做，不走 Opik 的 `.format()`。
    """
    if not is_enabled():
        return
    try:
        from opik import Prompt, opik_context

        cached = _prompt_cache.get(name)
        if cached is None or cached[0] != content:
            prompt = Prompt(name=name, prompt=content, validate_placeholders=False)
            _prompt_cache[name] = (content, prompt)
        else:
            prompt = cached[1]
        opik_context.attach_prompt_to_current_trace(prompt)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik prompt 註冊/連結失敗 name=%s", name)


def opik_trace_url(opik_trace_id: str, url_override: str) -> str:
    """由 Opik trace id 組出 UI 直達網址（後台 observability → Opik 深連結用）。

    用 opik 官方的 redirect 端點（跨版本穩定），把 opik 相依鎖在本套件內。
    id 或 url_override 為空即回空字串。
    """
    if not opik_trace_id or not url_override:
        return ""
    try:
        from opik.url_helpers import get_project_url_by_trace_id

        return get_project_url_by_trace_id(trace_id=opik_trace_id, url_override=url_override)
    except Exception:  # noqa: BLE001 - 組網址失敗不可影響後台
        logger.warning("組 Opik trace 網址失敗")
        return ""
