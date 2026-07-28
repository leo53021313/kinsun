"""這一輪對話的跨層事實：長輩的原話（agent→工具）與拿到的來源（工具→agent）。

兩者共用同一個機制、方向相反：原話讓工具分辨「長輩說的地點」與「模型猜的地點」；
來源登記簿讓出站防線分辨「金孫真的查到了」與「金孫自己編了一個機關名」。

## 長輩原話（elder_utterance）

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

## 本輪來源登記簿（turn_sources／record_source）

⚠️ 同樣是實測逼出來的（2026-07-26 全流程模擬）：該輪**零工具呼叫**的情況下，
金孫對長輩說「國健署網站說，在家裡要穿防滑鞋子」「查核中心說這是假的喔」——
冒用政府機關名義替它自己編的健康建議背書。提示詞改得再好也擋不住（那兩句正是
提示詞裡的範例字串被當成句型模板照抄），所以防線要在程式層。

登記的是「**有沒有拿到可引用的來源**」，不是「有沒有呼叫工具」——這個分別是關鍵：
目前沒有 active RAG release，衛教檢索每次都回「查不到」，若閘門寫成「呼叫過就放行」，
模型只要呼叫一次、拿到查不到、再照樣冒名，就能穿過防線。

`default=None`＝沒開帳本時 `record_source` 完全 no-op：排程端與既有工具測試
一字都不必改，工具也不需要知道自己在誰的回合裡跑。
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager

logger = logging.getLogger("kinsun.turn_context")

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


_sources: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "kinsun_turn_sources", default=None
)


@contextmanager
def turn_sources() -> Iterator[list[str]]:
    """在範圍內開一本本輪的來源登記簿。由 CareAgent 開、工具寫、出站防線讀。"""
    ledger: list[str] = []
    token = _sources.set(ledger)
    try:
        yield ledger
    finally:
        _sources.reset(token)


def record_source(name: str) -> None:
    """工具真的拿到可引用的外部來源時登記一筆；沒開帳本時 no-op。

    ⚠️ 只有「握有外部來源」的工具該呼叫（web_search 的網域、衛教檢索的 citation、
    新聞的媒體名）。天氣（Open-Meteo 不是氣象署）、路線、交通、排程都不該登記——
    它們沒有可以講給長輩聽的出處。
    """
    ledger = _sources.get()
    if ledger is not None and name:
        ledger.append(name)


_actions: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "kinsun_turn_actions", default=None
)


@contextmanager
def turn_actions() -> Iterator[list[str]]:
    """本輪**真的改變了系統狀態**的工具動作。

    ⚠️ 為什麼需要（2026-07-26 全流程模擬實測）：長輩交代「明天下午兩點四十五要去繳
    水電費」，金孫回「好呀，那我明天下午兩點四十五提醒您去繳水電費喔」——肯定句、
    不是徵詢——而該輪**沒有呼叫 create_schedule**，資料庫裡什麼都沒有（Opik 佐證）。
    七次明確請求裡有一次是這樣。

    對一個記憶輔助產品，這是最傷的一種錯：長輩把事情交給金孫之後就不會再自己記了。
    提示詞已經寫著「他答應了就用 create_schedule 記下來」，實測仍然漏——與來源冒用
    同源，提示詞管不住的事情要在程式層留證據。

    與 `turn_sources` 分開兩本帳，因為問的是不同的問題：來源問「有沒有拿到可引用的
    東西」，動作問「有沒有真的做」。混成一本會讓兩道防線互相誤放。
    """
    ledger: list[str] = []
    token = _actions.set(ledger)
    try:
        yield ledger
    finally:
        _actions.reset(token)


def record_action(name: str) -> None:
    """工具真的改變了系統狀態時登記一筆（用工具名）；沒開帳本時 no-op。

    只有**寫入成功**才登記——驗證失敗、找不到資料都不算做過。
    """
    ledger = _actions.get()
    if ledger is not None and name:
        ledger.append(name)


_announcer: contextvars.ContextVar[Callable[[list[str]], None] | None] = contextvars.ContextVar(
    "kinsun_tool_announcer", default=None
)


@contextmanager
def tool_announcer(callback: Callable[[list[str]], None]) -> Iterator[None]:
    """在範圍內接收「這一輪要呼叫哪些工具」的通知（spec 2026-07-28 P2）。

    ⚠️ 這是安撫話的觸發點，而它的時機**非常關鍵**：非同步回覆要在模型決定查什麼之後、
    工具真的跑之前，立刻讓長輩聽到一句「好，我幫您查一下喔」。那個時刻只存在於
    `CareAgent._run_tool_loop` 裡拿到 `tool_calls` 的那一瞬間——早一點還不知道要查
    什麼（挑不到貼合工具的句子），晚一點長輩已經多等了工具的時間。

    走 contextvars 而非改協定，理由與本模組其餘幾個一模一樣：只有 WebSocket 通道
    需要這個訊號，改 `CareAgent.handle` 的簽章會波及管線、排程端與所有測試替身。

    `default=None`＝沒有人在聽時 `announce_tools` 完全 no-op：LINE 通道、
    `POST /turns`、排程端與既有測試一字都不必改。
    """
    token = _announcer.set(callback)
    try:
        yield
    finally:
        _announcer.reset(token)


def announce_tools(tool_names: list[str]) -> None:
    """通知「這一輪要呼叫這些工具」；沒有人在聽時 no-op。

    ⚠️ 通知失敗**絕不可**中斷對話：安撫話是加分項，而這裡的呼叫端是長輩回覆路徑的
    正中央。callback 拋出的任何例外就地吞掉——最壞的情況只是這一輪沒有安撫話。
    """
    callback = _announcer.get()
    if callback is None or not tool_names:
        return
    try:
        callback(tool_names)
    except Exception:  # noqa: BLE001 - 安撫話失敗不可中斷長輩的回覆
        logger.warning("安撫話通知失敗，本輪不講安撫話")
