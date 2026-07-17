"""長輩這輪原話的傳遞：讓工具能分辨「長輩說的地點」與「模型自己猜的」。

⚠️ 為什麼需要它（實測逼出來的，2026-07-17）：模型不知道長輩在哪時，會**猜**
「台北市」去呼叫天氣工具，工具照查照回，金孫就很有自信地把台北的天氣報給
高雄的長輩（實測 4/7）。提示詞在工具描述與 system prompt 兩處都寫著「不要自行
假設台北」，它照做不誤——**這不是提示詞改得夠好就能解決的**。

同一份實測還揭穿一件事：舊版「金孫會開口問」根本不是模型在守規矩。它一直在猜，
只是猜的字串（「目前所在地」「您現在在哪個縣市呢？」）地理編碼查不到、工具回
「查不到」之後它才去問。那條防線是**意外的**——一旦它剛好猜中一個查得到的地名
（台北市），長輩就拿到別人的天氣。

故根治必須是結構性的：工具在沒有座標時，要能驗證地名確實來自長輩的原話。

走 contextvars 而非改工具協定，理由與 `llm.py` 的 `_usage_collector` 完全相同
（見該處註解）：改 `Callable[[dict], str]` 這個協定會波及所有工具與測試替身，
而只有天氣工具需要這個資訊；contextvars 讓需要的一方自取，且各執行緒／請求的
context 彼此隔離，併發回合不會互相污染。
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager

_utterance: contextvars.ContextVar[str] = contextvars.ContextVar(
    "kinsun_elder_utterance", default=""
)


@contextmanager
def elder_utterance(text: str) -> Iterator[None]:
    """在範圍內把長輩這輪的原話提供給工具。由 CareAgent 設定。"""
    token = _utterance.set(text)
    try:
        yield
    finally:
        _utterance.reset(token)


def current_utterance() -> str:
    """長輩這輪的原話；未設定時為空字串（如主動關懷、排程端）。"""
    return _utterance.get()
