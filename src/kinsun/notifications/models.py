"""App 內通知的呈現分級（2026-08-01，Leo 裁決）。

**這一層回答的問題只有一個**：收到這則通知的人，畫面上該不該被「打斷」。
不是「這件事有多嚴重」——那是 `safety/tiers.py` 的 `RiskTier`（L0／L1／L2）
在回答的問題，兩者刻意不共用同一套詞彙，理由見下。

⚠️ **為什麼不直接把 `RiskTier` 寫進 `app_notifications`**：
1. `RiskTier` 是**分級器對長輩這句話的判定**，只有危急偵測那條路徑產得出來；
   用藥提醒、回診提醒、每日主動關懷根本沒有「風險等級」可言，硬要給一個值
   等於逼三個無關的寫入點編造一個沒有意義的數字。
2. 反過來，通知該長什麼樣是**呈現層**的問題，未來可能有與風險完全無關的
   「打斷式」通知（如帳號被登出）。綁死在風險分級上，那些通知就無處可去。
3. `RiskTier` 的級距日後若再調整（L3 已經刪過一次，見 `safety/tiers.py`
   的 `tier_from_db`），不該連帶動到每一張已經發出去的通知的顯示方式。

⚠️ **值域刻意只有兩個**，且短期內不打算擴充：前端能畫的就是「一般」與
「紅色警報」兩種樣式（`web/src/notify/NotificationBanner.tsx`），多出來的第三
個值在畫面上無處著落。資料庫欄位型別是開放的 `TEXT`（不加 CHECK、不用 PG
enum），擴充時不必再跑一次 DDL 遷移——但**新增值的同時必須一併更新前端的
對照表**，否則前端會依 `severity_from_db` 的同一套保守規則把它當成一般通知。
"""

from __future__ import annotations

from enum import StrEnum


class NotificationSeverity(StrEnum):
    """通知的呈現分級。字面值即 API JSON 與資料庫欄位的值，三處完全一致。"""

    # 一般提醒／主動關懷：禮貌宣告，等螢幕報讀軟體念完手邊的東西再播報。
    NOTICE = "notice"
    # 危急警報：紅色樣式＋打斷式宣告（role="alert"／aria-live="assertive"）。
    ALERT = "alert"


def severity_from_db(value: str) -> NotificationSeverity:
    """讀 DB 的 severity 欄：認不得的值一律當成一般通知，不拋例外。

    ⚠️ 比照 `safety/tiers.py::tier_from_db` 的既有作法。認不得的值有兩種來源：
    ①舊資料（2026-08-01 之前寫入的列，遷移時一律填 `notice`，見 `db.py`）；
    ②未來新增了值、但這支程式是舊版本。兩種情形都不該讓「讀取通知列表」這個
    唯讀端點回 500——通知讀不到比通知樣式不對嚴重得多。
    """
    try:
        return NotificationSeverity(value)
    except ValueError:
        return NotificationSeverity.NOTICE
