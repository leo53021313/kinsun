"""安撫話語庫：模型決定要查東西時，先唸給長輩聽的那一小句。

## 為什麼是預錄而不是讓模型講（2026-07-28 語料實測，n=55 真實回應）

非同步工具調用下，長輩問完到聽見答案有 9.5 秒（實測中位數：LLM 決定工具 2.22s
＋工具 2.25s ＋ LLM 消化 1.75s ＋ TTS 首段 3.29s），中間耳朵裡是全然的安靜。
先講一句「好，我幫您查一下喔」能把第一個聲音提前到 2.22 秒。

原設計是讓模型在「決定呼叫哪個工具」的同一次回應裡附上這句話。語料推翻了它的前提：

- **65%（36/55）去掉結尾標點後一字不差都是「好，我幫您查一下喔」**。逐工具看更極端：
  `web_search` 6/6、`search_nearby_places` 5/5 全部是通用句。
- 剩下 35% 的「情境」，變化**全部來自工具本身**（「查一下最近的新聞」「查一下車程」
  「看一下有哪些行程」），不是來自長輩講了什麼。模型沒有在貼合對話，它只是把工具的
  名詞塞進同一個句型——而那正是本檔逐工具備句能給的東西。
- 模型生成還要多付一次 TTS（實測 1.86 秒，佔改後延遲的 46%），並帶來兩種只有它才有的
  失效：把內部敘述寫進答案通道（實錄「好，我幫您查一下喔。碎碎唸：呼叫 `get_news`
  工具來取得最近的新聞標題。」），以及在工具還沒跑時就對長輩斷言結果（實錄
  「好，我馬上幫您記下來。晚上七點記得吃血壓藥喔！」——`create_schedule` 尚未執行）。

⚠️ **「貼合情境」與「劇透」是同一個行為**：模型越往具體內容靠，越容易在工具還沒跑時
就講出結果。改成我們自己寫的句子，這兩種失效從源頭消失，不需要任何出站防線。

## 兩個維度：人設 × 工具

日後會加入不同人設風格，故語庫是二維的。兩軸各有保底，**缺任何一格都不會壞，
只會變得比較籠統**：人設不存在 → 退回 `DEFAULT_PERSONA`；工具沒配句子 → 退回該人設的
`generic`。

⚠️ 只有**文字**住在這裡，音檔不進版控——它由當前 TTS 設定自動合成並快取
（見 `speech/ack_audio.py`）。這是為了語音克隆：換聲音只要改 `TTS_VOICE_VERSION`，
十幾段音檔自動重生，零手工步驟、零重錄。

## 新增工具時不會漏掉

`tests/test_speech_acks.py` 以 `pkgutil` 走遍 `kinsun.tools` 蒐集**每一個**模組級
`ToolSpec`，斷言 `DEFAULT_PERSONA` 的 `by_tool` 每個工具都有一格——新增工具檔會自動
被納入掃描，漏配 CI 就紅。故新增工具時**必須**回來這裡表態，即使結論是「用通用句」
（那就寫 `USE_GENERIC`，讓「刻意如此」與「忘了寫」在程式碼上看得出差別）。
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass

# 明講「這個工具刻意用通用句」。與「忘了加這一格」在程式碼上必須看得出差別——
# 後者會被測試擋下，前者是經過判斷的決定。
USE_GENERIC: tuple[str, ...] = ()


@dataclass(frozen=True)
class AckPersona:
    """一個人設的安撫話。`generic` 必填（保底），`by_tool` 逐工具覆寫。"""

    generic: tuple[str, ...]
    by_tool: Mapping[str, tuple[str, ...]]


DEFAULT_PERSONA = "kinsun"

# ⚠️ 每一句都會被 TTS 原封唸出來，故：
#   - 台灣繁體中文口語，晚輩對阿公阿嬤講話的語氣
#   - 9～16 字（語料實測合格區間；TTS 是 0.9 秒固定成本＋每字 0.10 秒）
#   - 不含任何符號、英文、機關名
#   - **只能說「正在查」，絕不可說「已經查好／已經記好」**——這句話是在工具**還沒跑**
#     的時候唸出去的，說已完成而工具隨後失敗，等於對長輩說謊（語料實錄過這種洩漏）
_PERSONAS: dict[str, AckPersona] = {
    DEFAULT_PERSONA: AckPersona(
        generic=(
            "好，我幫您查一下喔",
            "好，我看看喔",
            "稍等一下下喔",
        ),
        by_tool={
            # 語料裡模型自己的變化就是這些，照抄即可——沒有觀測到的變化不要憑空發明。
            "get_news": ("好，我幫您看看最近的新聞喔", "我看看今天有什麼消息喔"),
            "get_news_detail": ("好，我幫您看看那一則喔", "我再看仔細一點喔"),
            "get_weather": ("好，我幫您看一下天氣喔",),
            "search_nearby_places": ("好，我幫您找找看附近有什麼喔", "我看看附近喔"),
            "get_route": ("好，我幫您看一下怎麼去喔", "我看看要走多久喔"),
            "get_bus_arrival": ("好，我幫您看一下公車喔",),
            "get_mrt_line": ("好，我幫您看一下捷運喔",),
            "get_parking": ("好，我幫您找找看停車位喔",),
            "health_education_rag": ("好，這個我幫您查一下喔",),
            # 語料 6/6 模型自己也用通用句——查證的主題五花八門，逐句備反而不自然。
            "web_search": USE_GENERIC,
            # ⚠️ 排程三兄弟一律用「看／記一下」這種**進行中**的講法，不可寫成
            # 「記好了」「幫您取消了」：工具還沒跑，說完成就是說謊。
            "create_schedule": ("好，我幫您記一下喔",),
            "list_schedules": ("好，我幫您看一下您的行程喔",),
            "cancel_schedule": ("好，我幫您看一下喔",),
        },
    ),
}


def personas() -> frozenset[str]:
    """目前定義了哪些人設。"""
    return frozenset(_PERSONAS)


def persona(name: str = DEFAULT_PERSONA) -> AckPersona:
    """取一個人設；不存在就退回預設人設（不拋例外——安撫話是加分項）。"""
    return _PERSONAS.get(name) or _PERSONAS[DEFAULT_PERSONA]


def phrases_for(tool_name: str, *, persona_name: str = DEFAULT_PERSONA) -> tuple[str, ...]:
    """這個工具的候選安撫話；沒配（或刻意 `USE_GENERIC`）就退回該人設的通用句。"""
    chosen = persona(persona_name)
    return chosen.by_tool.get(tool_name) or chosen.generic


def pick(
    tool_name: str,
    *,
    persona_name: str = DEFAULT_PERSONA,
    rng: random.Random | None = None,
) -> str:
    """隨機挑一句。輪替是為了不讓長輩每一輪都聽到同一個音檔。

    `rng` 可注入，測試才能確定性地驗行為（同 `tools/news.py` 的慣例）。
    """
    candidates = phrases_for(tool_name, persona_name=persona_name)
    if not candidates:  # 防呆：人設的 generic 被寫空時不要炸，改成這輪不講。
        return ""
    return (rng or random).choice(candidates)


def all_phrases() -> tuple[str, ...]:
    """語庫裡所有相異的句子，供啟動時預熱音檔快取用（順序穩定，方便比對）。"""
    seen: dict[str, None] = {}
    for one in _PERSONAS.values():
        for phrase in (*one.generic, *(p for group in one.by_tool.values() for p in group)):
            seen[phrase] = None
    return tuple(seen)
