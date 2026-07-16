"""自適應問候時間的計算核心：從長輩的活躍時刻推算下一次的問候時間。

⚠️ 安全界線（不可協商）：本模組只決定「早安問候」的時間。用藥提醒
（medications/jobs.py）與回診提醒（appointments/jobs.py）是各自獨立的 cron，
時間由 MEDICATION_*_HOUR／APPOINTMENT_REMINDER_HOUR 決定，永遠不受本模組影響。

⚠️ 死區（dead zone）是唯一擋住自我實現漂移的設計，不要拿掉：
若規則是「問候＝她第一次活躍的時刻」，而她的活躍根本是被我們的問候觸發的
（九點問候 → 她九點五分講話），時間會逐日往「後」漂：
    09:00 → 她 09:05 活躍 → 09:30 → 她 09:35 → 10:00 → ... → 一路漂到上限。
（已用突變測試驗證：拿掉死區，漂移測試會漂到 11:00 並失敗。）
故只有當中位活躍時刻與現行問候時間**相差超過死區門檻**才調整。

⚠️ 兩個方向的死區門檻刻意不對稱（Leo 核定），因為**兩個方向的訊號品質根本不同**：

* 她在問候「之前」就自己來了 ＝ **乾淨訊號**。問候還沒發出，她的活躍不可能是
  我們觸發的，她確實醒著。→ 死區用 max_shift_minutes（30 分）。
* 她在問候「之後」才有動靜 ＝ **模糊訊號**。可能是還沒醒，也可能只是慢慢看手機
  （手機放在另一個房間，照護場域很常見）。**兩者在資料上分不出來**——要分出來就
  得試探，而 Leo 已核定不試探。→ 死區用 lag_tolerance_minutes（60 分），更保守。

沒有這個不對稱，「習慣四十五分鐘後才看手機」的長輩會被系統推著跑：45 分 > 30 分
→ 判定太早 → 往後調 → 她還是 45 分後才看 → 再往後 → 一路推到上限，最終「十一點
問候、十一點四十五她才回」，比原本「八點問候、八點四十五回」更糟，而且「早安」
變成將近中午。（回歸測試：test_a_forty_five_minute_response_lag_no_longer_drifts。）

步伐大小兩個方向都仍是 max_shift_minutes：不對稱的是「要不要動」，不是「動多少」。

收斂點＝中位活躍時刻 − lag_tolerance_minutes（往後）或 ＋ max_shift_minutes
（往前），即死區邊緣，或先撞到的護軌：她十一點才活躍 → 08:00 逐日往後停在 10:00；
她七點就自己來 → 08:00 往前停在 07:30（不是 07:00——死區讓它停在離中位數 30 分處）。

⚠️ 殘留限制：容忍度只把自我實現迴圈的門檻從 30 分抬到 60 分，沒有根治它。若她固定
在問候後 90 分（> 容忍度）才回話，時間仍會逐日往後漂，最後由上限接住。要根治得比對
問候實際送出的時刻，而 first_user_turn_per_day 這個訊號沒有那個資訊——已知限制。
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from statistics import median

# 問候 job 每半小時掃一次（cron 0,30 * * * *），故偏好時間必須落在整點或半點——
# 存 07:45 卻在 08:00 問候，是對後台說謊。
_SLOT_MINUTES = 30


def median_minute_of_day(first_turns: list[float], tz: tzinfo) -> int:
    """把每筆時刻換算成「當天的第幾分鐘」後取中位數。

    用中位數不用平均數：偶爾的熬夜或早起是離群值，中位數對它有抗性。

    first_turns 為空時會拋 StatisticsError——呼叫端要寫可解釋性欄位前請先確認有資料
    （next_greeting_time 可能在沒有任何樣本時仍回傳「把違規時間拉回護軌」的結果）。

    已知限制：minute_of_day 是線性座標、不是環狀座標。若她的活躍時刻橫跨午夜
    （23:50 與 00:10 交錯），中位數在數學上會失去意義。此時靠護軌把結果關在界內。
    """
    minutes = []
    for ts in first_turns:
        local = datetime.fromtimestamp(ts, tz)
        minutes.append(local.hour * 60 + local.minute)
    return int(median(minutes))


def _align(minute_of_day: int) -> int:
    return round(minute_of_day / _SLOT_MINUTES) * _SLOT_MINUTES


def next_greeting_time(
    *,
    first_turns: list[float],
    current: tuple[int, int],
    tz: tzinfo,
    min_sample_days: int,
    earliest_hour: int,
    latest_hour: int,
    max_shift_minutes: int,
    lag_tolerance_minutes: int,
) -> tuple[int, int] | None:
    """算出下一次的問候時間；回 None 代表不調整（樣本不足、或已在死區內）。

    first_turns 為她每天第一則主動訊息的時刻（epoch 秒），current 為現行問候時間。

    max_shift_minutes 是步伐大小（兩個方向共用）＋往「前」調的死區門檻；
    lag_tolerance_minutes 是往「後」調的死區門檻，必須 ≥ max_shift_minutes
    （由 Task C 的跨欄位驗證保證）。兩者不對稱的理由見模組 docstring——那是本模組
    最容易被「順手統一」掉的設計，改動前請先讀。

    後置條件：回傳值必定落在 [earliest_hour:00, latest_hour:00] 內；
    回 None ⇔ current 已在護軌內。
    """
    current_minutes = current[0] * 60 + current[1]

    # 護軌是絕對的，不以「有沒有資料」為條件：現行時間在護軌外就先拉回界內。
    # 若讓死區先短路，五點就活躍的長輩（diff = 0 落在死區）會被永遠釘死在
    # 違規的五點——而護軌存在的意義，正是為了保護這種長輩。
    # 可達路徑：PROACTIVE_GREETING_HOUR 未受 earliest／latest 的跨欄位驗證涵蓋。
    bounded = max(earliest_hour * 60, min(latest_hour * 60, current_minutes))
    if bounded != current_minutes:
        return divmod(bounded, 60)

    if not first_turns or len(first_turns) < min_sample_days:
        return None

    target = median_minute_of_day(first_turns, tz)
    diff = target - current_minutes
    # 死區：夠近了就不動，這是擋住自我實現漂移的關鍵。兩個方向的門檻刻意不同——
    # 「問候後才有動靜」是模糊訊號（分不出「還沒醒」與「只是慢慢看手機」），故往後
    # 調要比往前調保守。詳見模組 docstring，不要把兩者統一。
    tolerance = lag_tolerance_minutes if diff > 0 else max_shift_minutes
    if abs(diff) <= tolerance:
        return None

    step = max_shift_minutes if diff > 0 else -max_shift_minutes
    moved = _align(current_minutes + step)
    clamped = max(earliest_hour * 60, min(latest_hour * 60, moved))
    if clamped == current_minutes:
        return None  # 已在護欄邊界上，無處可去
    return divmod(clamped, 60)
