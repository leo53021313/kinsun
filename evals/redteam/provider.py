"""promptfoo 的自訂 Python provider：讓紅隊工具直接打我們真正的 CareAgent。

promptfoo 會以「持續存在的 worker 程序」載入本檔一次，之後每題呼叫一次 `call_api`
（見 https://www.promptfoo.dev/docs/providers/python/），故受測系統只組裝一次、
放模組層快取。

受測對象與 Opik 實驗共用 `evals/subject.py`（真 CareAgent、不碰 DB、審核依旗標），
兩邊量的是同一個東西——這正是把組裝抽出去的原因。

sys.path 自己補：promptfoo 由 Node 端起 Python 程序，工作目錄與 `PYTHONPATH` 都不保證，
故以本檔位置回推 repo 根目錄與 `src/`，讓 `evals.*` 與 `kinsun.*` 都匯入得到。
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (_REPO_ROOT, _REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import hashlib  # noqa: E402
import json  # noqa: E402

from evals.subject import build_reply_fn  # noqa: E402
from kinsun import tracing  # noqa: E402
from kinsun.config import load_dotenv, load_settings  # noqa: E402

_reply_to = None


def parse_turn(prompt: str) -> tuple[str, str]:
    """把 promptfoo 傳來的 prompt 解析成 (對話鍵, 本輪要處理的訊息)。

    多輪 strategy（crescendo 等）傳來的是 JSON 對話陣列 `[{role, content}, ...]`；
    單輪則是純字串。兩者都走同一個 `call_api`，故必須自行辨別。

    ⚠️ 這件事沒做對，多輪測試就是**假的**：對話鍵原本取「本輪訊息」的雜湊，等於每一
    輪都換一位長輩，短期記憶完全累積不起來——而多輪綁架的攻擊面正是「前幾輪的內容會
    進入下一輪的 system prompt」。對話鍵改取**第一則訊息**，整串對話才共用同一位長輩。

    只回傳最後一則使用者訊息：前幾輪在先前的呼叫中已經進過 agent、也已寫入短期記憶，
    重放會讓同一句話被記兩次。此法依賴 promptfoo 依序呼叫同一個常駐 worker
    （設定中的 `workers: 1`）；亂序或重試會讓記憶與 promptfoo 的對話不同步，這是評測
    harness 可接受的取捨，正式管線不受影響。
    """
    try:
        messages = json.loads(prompt)
    except (json.JSONDecodeError, TypeError):
        return _conversation_key(prompt), prompt
    if not isinstance(messages, list) or not messages:
        return _conversation_key(prompt), prompt
    contents = [
        str(m.get("content", "")) for m in messages if isinstance(m, dict) and "content" in m
    ]
    if not contents:
        return _conversation_key(prompt), prompt
    user_contents = [
        str(m.get("content", ""))
        for m in messages
        if isinstance(m, dict) and m.get("role") in (None, "user")
    ]
    return _conversation_key(contents[0]), (user_contents or contents)[-1]


def _conversation_key(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _ensure_ready():
    """第一次呼叫時才組裝，之後重用（worker 常駐，不必每題重建 client）。"""
    global _reply_to
    if _reply_to is None:
        import os

        load_dotenv()
        settings = load_settings(os.environ)
        # 尊重 OPIK_ENABLED：想讓紅隊的幾百筆 trace 不要洗掉 Opik 專案，
        # 跑之前設 OPIK_ENABLED=false 即可。
        tracing.configure(settings)
        _reply_to = build_reply_fn(settings)
    return _reply_to


def call_api(prompt: str, options: dict, context: dict) -> dict:
    """promptfoo 的必要介面：一題攻擊進、金孫的回覆出。

    例外一律轉成 `{"error": ...}` 回報而非往外拋——紅隊動輒數百題，Gemini 免費層
    429 幾乎必然發生，一題炸掉不該讓整輪掃描中止。promptfoo 會把 error 標成該題失敗
    並繼續跑。
    """
    try:
        conversation_key, message = parse_turn(prompt)
        return {"output": _ensure_ready()(message, conversation_key)}
    except Exception as exc:  # noqa: BLE001 - 單題失敗不可中止整輪掃描
        return {"error": f"{type(exc).__name__}: {exc}"}
