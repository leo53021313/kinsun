"""`scripts/kinsun.sh` 的自我說明與它實際支援的服務清單必須一致。

⚠️ 這條守的症狀是「`start web` 明明可以用，`usage` 卻查不到 web」——使用者只會
相信他看得到的那一份清單，於是新加的服務等於不存在。網頁版前端（P1）就是這樣
被漏掉的：`START_ORDER` 加了 `web`，usage 那一行沒跟著改。純文件漂移，程式一切
正常，所以不會有任何測試紅給你看——除非有這一條。
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "kinsun.sh"


def _matched(pattern: str) -> str:
    match = re.search(pattern, SCRIPT.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None, f"在 {SCRIPT.name} 找不到 {pattern}"
    return match.group(1)


def test_usage_的服務名清單與_start_order_逐項一致():
    # 全形空白（U+3000）也算空白，str.split() 切得動。
    usage_services = _matched(r"^服務名：(.+)$").split()
    start_order = _matched(r"^START_ORDER=\(([^)]*)\)").split()
    assert usage_services == start_order
