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
import time
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


_pending: contextvars.ContextVar[Callable[[], list[str]] | None] = contextvars.ContextVar(
    "kinsun_pending_utterances", default=None
)


@contextmanager
def pending_utterances(provider: Callable[[], list[str]]) -> Iterator[None]:
    """在範圍內提供「這位長輩還有哪些話正在處理中」（spec 2026-07-28 P3）。

    ⚠️ 為什麼需要（併發對話的核心難題）：長輩問完新聞（要查、慢），三秒後接著問
    「**那**天氣呢」——「那」是指代，需要上文。但新聞那一輪還沒寫進 `turns` 表
    （記憶只在回覆產生後才寫），天氣這一輪組裝情境時**看不到他剛問過新聞**，
    模型只好反問「您是說哪個的天氣」。

    刻意**不採**「長輩的話先寫 DB、回覆後再補」：那會違反既有安全契約——被濫用審核
    攔下的那一輪不寫進記憶（`pipeline.py` 的順序守門，綁架企圖不該變成明天的對話
    脈絡）。在途清單只活在記憶體、被攔的輪直接丟棄，契約完好。

    傳的是 **provider 而不是清單**：在途集合隨時在變，要在組裝的那一刻才取值，
    不是進入 context 的那一刻。
    """
    token = _pending.set(provider)
    try:
        yield
    finally:
        _pending.reset(token)


def current_pending_utterances() -> list[str]:
    """這位長輩還在處理中的其他問句；沒有人提供時為空清單。

    取值失敗一律當成沒有——情境是加分項，不可讓它擋住長輩的回覆。
    """
    provider = _pending.get()
    if provider is None:
        return []
    try:
        return list(provider())
    except Exception:  # noqa: BLE001 - 在途清單失敗不可中斷對話
        logger.warning("在途清單讀取失敗，本輪不注入")
        return []


_directive: contextvars.ContextVar[str] = contextvars.ContextVar(
    "kinsun_turn_directive", default=""
)


@contextmanager
def turn_directive(text: str) -> Iterator[None]:
    """在範圍內追加一句只對這一輪生效的系統指示（spec 2026-07-28 P3）。

    用途是「晚到答案的回指」：長輩連問幾個問題時，慢的那個答案回來時他早就在講
    別的了，開頭要自然帶一句「對了，您剛剛問的新聞喔……」。

    ⚠️ 走系統提示而不是在程式層硬前綴：拼接出來的句子 TTS 唸起來會斷裂，而這句話
    要讓長輩覺得是金孫自己想起來的。模型不聽時不做補救——為了這件事把對話弄壞是
    更差的結果（同 `_repair_empty_promise` 的「只補救一次」）。
    """
    token = _directive.set(text)
    try:
        yield
    finally:
        _directive.reset(token)


def current_turn_directive() -> str:
    return _directive.get()


_transcript_listener: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar(
    "kinsun_transcript_listener", default=None
)


@contextmanager
def transcript_listener(callback: Callable[[str], None]) -> Iterator[None]:
    """在範圍內接收「這一輪長輩說了什麼」（spec 2026-07-28 P3）。

    通知時機是 `CareAgent.prepare`——ASR 剛完成、情境還沒組完的那一刻。這正是
    在途清單需要的時間點：下一輪（長輩緊接著問的那句）組裝情境時就看得到這一句。
    """
    token = _transcript_listener.set(callback)
    try:
        yield
    finally:
        _transcript_listener.reset(token)


def announce_transcript(text: str) -> None:
    """通知本輪長輩的原話；沒有人在聽時 no-op、失敗就地吞掉。"""
    callback = _transcript_listener.get()
    if callback is None or not text:
        return
    try:
        callback(text)
    except Exception:  # noqa: BLE001 - 在途登記失敗不可中斷對話
        logger.warning("在途原話登記失敗")


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


_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "kinsun_turn_deadline", default=None
)


@contextmanager
def turn_budget(seconds: float) -> Iterator[None]:
    """在範圍內給這一輪一個總時間預算。由 `pipeline` 在收到長輩這句話時設定。

    ⚠️ 為什麼需要它（2026-07-28 實錄逼出來的）：一輪對話會依序打三次 Gemini
    （危急分級→濫用審核→生成回覆；`SAFETY_COMBINED_CLASSIFIER_ENABLED` 開啟時前兩次
    併成一次、變兩次），每一次各有自己的 30 秒逾時。Gemini 3.5 過載
    那晚，三次**各自**卡滿 30 秒才放棄，長輩按完對講機盯著螢幕 **96.6 秒**才聽到
    「我現在有點狀況」——逐次逾時管得住單一次呼叫，管不住它們相加。

    走 contextvars 而非把 deadline 一路當參數傳下去，理由與本檔其餘機制相同：
    明式傳遞要改 `RiskDetector.assess`／`AbuseModerator.moderate`／`CareAgent.handle`
    等六七個簽名與其全部測試替身，而真正需要這個資訊的只有 `llm.py` 一處出口。

    用 `time.monotonic` 而非 wall clock：系統校時（NTP 跳秒、夏令時間）不該讓
    長輩這一輪突然被判出局。
    """
    token = _deadline.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining_budget() -> float | None:
    """本輪還剩幾秒；`None`＝沒開預算（排程端、主動關懷、既有測試）＝不限制。

    ⚠️ 超支時回**負數**而不夾在 0：呼叫端要分得出「剛好用完」與「已經超支 60 秒」，
    後者是要記進日誌追的異常。`None` 與 `0` 也絕不可混為一談——前者是「沒有預算
    這回事」，後者是「預算用完了」，兩者的正確行為完全相反。
    """
    deadline = _deadline.get()
    if deadline is None:
        return None
    return deadline - time.monotonic()


_inline_audio: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "kinsun_inline_audio_delivery", default=False
)


@contextmanager
def inline_audio_delivery(enabled: bool) -> Iterator[None]:
    """這一輪的音檔會不會直接走長連線交回通道（C1 內嵌投遞）。由 `dispatch` 設定。

    ⚠️ 為什麼 `pipeline` 需要知道（2026-08-01）：分段只在**投遞端接得住**時才有意義。
    WS 通道能逐段推，`POST /turns` 只能回一則——後者若照樣分段，長輩就只拿得到第一句，
    其餘永遠取不回來（REST 續拉端點已隨 2026-08-01 續段語音 WS 直送移除）。而兩條路徑
    的 `channel` 同為 `app`，`_chunked_channels` 分不出來。

    走 contextvars 而非改 `pipeline.process` 簽章，理由與本模組其餘六個機制相同：
    改簽章會波及所有測試替身與呼叫端，而真正需要這個資訊的只有 `_synthesize` 一處。

    `default=False`＝沒有人宣告時**不分段**。這是安全側：漏標的呼叫端會拿到完整音檔
    （慢一點但完整），而不是只拿到第一句、其餘無聲消失。
    """
    token = _inline_audio.set(enabled)
    try:
        yield
    finally:
        _inline_audio.reset(token)


def is_inline_audio_delivery() -> bool:
    return _inline_audio.get()
