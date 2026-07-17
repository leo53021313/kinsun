"""主動問候接續昨天話題的行為驗證探針：用真的 Gemini 驗證摘要注入的實際效果。

為什麼需要它：單元測試只能驗「摘要有沒有進到 prompt」，驗不到「金孫拿它幹嘛」。
本功能的核心風險是假 LLM 照不出來的那一型：
1. 摘要是**寫給家屬看的第三人稱敘述**（「阿嬤今天心情不錯，聊到孫子……」），卻被
   貼進金孫的 system prompt。模型可能照著複述成「根據記錄，您昨天心情不錯」這種
   讀報告的語氣，對長輩來說比罐頭問候更怪。
2. 摘要可能是**好幾天前**的（失聯關心的門檻就是 2 天沒開口），模型若當成剛發生的
   事，會講出自相矛盾的話。

2026-07-17 首次跑本探針即揪出設計錯：複驗 3 讓金孫說出「妳好久沒找我聊天了……
孫子這週末要回去」——追根發現當時的實作是讀「昨天的摘要」，而想念推播的觸發條件
（≥2 天沒開口）與「昨天有她的對話」互斥，那條路根本是死的。修正為讀「她上次開口
那天」＋明講距今幾天。

⚠️ 任何人改了 `agent.py` 的 `_recall_title`／`Recall` 或 `proactive` 的注入方式，都該重跑。

⚠️ 刻意不碰任何資料庫：短期／長期記憶全用測試替身，摘要直接以字串餵入
（正式路徑由 `worker._recall` 以 last_active 定位日期、再從 conversation_summaries 讀）。
只有 Gemini 是真的。DATABASE_URL 指向正式庫，絕不參與。

用法：uv run python scripts/recall_probe.py
需要：.env 裡的 GEMINI_API_KEY
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from kinsun.agent import CareAgent, Recall  # noqa: E402
from kinsun.config import load_dotenv, load_settings  # noqa: E402
from kinsun.llm import GeminiClient  # noqa: E402
from kinsun.memory.models import MemoryItem  # noqa: E402
from kinsun.memory.recall import SessionMemory  # noqa: E402
from kinsun.proactive.jobs import GREETING_INTENT, INACTIVITY_INTENT  # noqa: E402
from tests.fakes import FakeLongTermStore, FakeMemoryStore  # noqa: E402


def _agent(memories: list[MemoryItem] | None = None) -> CareAgent:
    settings = load_settings(os.environ)
    llm = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout_seconds,
    )
    # 長期記憶餵健康罐頭：這正是本功能之前，問候唯一撈得到的東西。
    session = SessionMemory(FakeMemoryStore(), FakeLongTermStore(memories or []))
    return CareAgent(llm, session)  # proactive 不跑工具迴圈，故不給 tools


_HEALTH_CANNED = [
    MemoryItem(text="長者有高血壓，每天早上吃降血壓藥", provenance="長者自述", date="2026-06-20"),
    MemoryItem(text="長者下週三要回診心臟科", provenance="長者自述", date="2026-07-05"),
]

_LAST_CHAT = "阿嬤今天心情不錯，聊到孫子這個週末要來看她，很期待。也提到膝蓋最近比較不痛了。"

CASES = [
    (
        "複驗 1：昨天聊過 → 早安問候",
        GREETING_INTENT,
        Recall(_LAST_CHAT, 1),
        "應自然接續孫子或膝蓋的話題，像晚輩記得昨天聊過。"
        "\n    ⚠️ 若出現「根據記錄」「系統顯示」「摘要」或整句複述 → 讀報告語氣，"
        "\n       段首的「不必逐字複述」沒擋住，需重寫措辭。"
        "\n    ⚠️ 若只講吃藥／回診、完全不提昨天 → 注入沒發揮作用，等同修之前。",
    ),
    (
        "複驗 2：她從沒開口過（新長輩）→ 早安問候",
        GREETING_INTENT,
        None,
        "應為單純的問候（可能提到吃藥／回診＝長期記憶裡僅有的東西）。"
        "\n    這就是本功能修之前的樣子，留作對照組。"
        "\n    ⚠️ 若憑空提到孫子 → 模型在編，比罐頭嚴重得多。",
    ),
    (
        "複驗 3：五天沒開口 → 想念（真實情境：失聯門檻 2 天，摘要必然是舊的）",
        INACTIVITY_INTENT,
        Recall(_LAST_CHAT, 5),
        "應表達想念，並把五天前的事當「上次」講、留餘地（例如問孫子後來有沒有來）。"
        "\n    ⚠️ 若講成「孫子這週末要來」當成還沒發生 → 把舊摘要當成剛剛的事，"
        "\n       days_ago 沒發揮作用（這正是 2026-07-17 探針第一次跑出來的錯）。"
        "\n    ⚠️ 若同時說「好久沒聊」又說「你昨天說」→ 自相矛盾，段首措辭要再修。",
    ),
]


def main() -> None:
    load_dotenv()
    print("長期記憶（固定）：" + "；".join(m.text for m in _HEALTH_CANNED))
    for title, intent, recall, expectation in CASES:
        print("=" * 76)
        print(title)
        print(f"  上次聊天：{f'{recall.days_ago} 天前｜{recall.content}' if recall else '（無）'}")
        print(f"  intent：　{intent}")
        print(f"  預期：　　{expectation}")
        try:
            reply = _agent(_HEALTH_CANNED).proactive("e1", intent, recall=recall)
        except Exception as exc:  # noqa: BLE001 - 探針：任何失敗都要看得到
            print(f"  ✗ 失敗：{type(exc).__name__}: {exc}")
            continue
        print(f"  金孫說：　{reply}")
    print("=" * 76)


if __name__ == "__main__":
    main()
