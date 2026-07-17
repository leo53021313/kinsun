"""地點功能的行為驗證探針：用真的 Gemini 驗證「GPS 是線索，不是答案」。

為什麼需要它：單元測試抓不到這個功能的核心風險。它的兩個致命 bug 都是「兩段
提示詞矛盾 → 模型選保守解」這一型——假 LLM 不會推理，兩段矛盾的提示詞在它眼裡
只是兩個字串。2026-07-17 就是靠這支探針才發現定位功能整整一天沒有作用
（agent.py 的 SYSTEM_PROMPT 改了、WEATHER_SPEC 的 description 沒跟著改）。

⚠️ 任何人改了 `tools/weather.py` 的 WEATHER_SPEC.description 或 `agent.py` 的
地點三句，都該重跑這支。兩者必須語意一致。

⚠️ 刻意不碰任何資料庫：短期／長期記憶與地點全用測試替身，只有 Gemini 與
Open-Meteo 是真的。DATABASE_URL 指向正式庫，絕不參與。

用法：uv run python scripts/anchoring_probe.py
需要：.env 裡的 GEMINI_API_KEY
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from kinsun.agent import CareAgent  # noqa: E402
from kinsun.composition import build_tool_registry  # noqa: E402
from kinsun.config import load_dotenv, load_settings  # noqa: E402
from kinsun.llm import GeminiClient  # noqa: E402
from kinsun.locations.facts import LocationFacts  # noqa: E402
from kinsun.locations.store import ElderLocation, FakeLocationStore  # noqa: E402
from kinsun.memory.recall import SessionMemory  # noqa: E402
from tests.fakes import FakeLongTermStore, FakeMemoryStore  # noqa: E402

TPE = timezone(timedelta(hours=8))

# 台南市的模糊座標（0.01 度），即 App 會送上來的形式。
_TAINAN = (22.99, 120.21)


def _now() -> datetime:
    return datetime.now(TPE)


def _agent(place: str | None):
    settings = load_settings(os.environ)
    llm = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout_seconds,
    )
    locations = FakeLocationStore()
    if place is not None:
        locations.save(
            ElderLocation("e1", place, _now().timestamp() - 180, *_TAINAN)  # 3 分鐘前
        )
    session = SessionMemory(
        FakeMemoryStore(),
        FakeLongTermStore(),
        facts=[
            LocationFacts(
                locations,
                clock=_now,
                stale_after_hours=settings.location_stale_after_hours,
            )
        ],
    )
    tools = build_tool_registry(clock=_now, rag_service=object(), tavily_api_key="")
    return CareAgent(llm, session, tools=tools)


CASES = [
    (
        "複驗 1：允許定位 → 問所在地天氣",
        "台南市",
        "今天天氣如何？",
        "應直接答台南的天氣（七月約 26–33°C），不反問。"
        "\n    ⚠️ 若反問 → Bug 2 復發（工具描述與 system prompt 又矛盾了）。"
        "\n    ⚠️ 若答約 19–27°C → 地理編碼的 countryCode=TW 被拿掉了（那是山西的氣溫）。",
    ),
    (
        "複驗 2：無位置（等同拒絕定位）→ 問天氣",
        None,
        "今天天氣如何？",
        "應開口問是哪裡。",
    ),
    (
        "複驗 3：允許定位 → 問別處（anchoring 防線）",
        "台南市",
        "我等一下要去別的地方吃飯，那邊天氣怎麼樣？",
        "應開口問是哪裡，不可拿台南去查。"
        "\n    ⚠️ 若直接答台南 → anchoring 失效，那是設計層級的問題："
        "\n       正確的反應是回頭重估工具方案（見 spec 2026-07-17-長輩目前地點），"
        "\n       不是往 prompt 疊更多句提示詞。",
    ),
]


def main() -> None:
    load_dotenv()
    for title, place, question, expectation in CASES:
        print("=" * 76)
        print(title)
        print(f"  情境位置：{place or '（無）'}")
        print(f"  長輩說：　{question}")
        print(f"  預期：　　{expectation}")
        try:
            reply = _agent(place).handle("e1", question)
        except Exception as exc:  # noqa: BLE001 - 探針：任何失敗都要看得到
            print(f"  ✗ 失敗：{type(exc).__name__}: {exc}")
            continue
        print(f"  金孫答：　{reply}")
    print("=" * 76)


if __name__ == "__main__":
    main()
