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

import logging
from collections.abc import Callable
from datetime import datetime, tzinfo
from statistics import median

from kinsun.memory.shortterm import MemoryStore, previous_day_bounds
from kinsun.proactive.preferences import (
    NO_SAMPLE_MEDIAN,
    GreetingPreference,
    GreetingPreferenceStore,
)

logger = logging.getLogger("kinsun.proactive.greeting_time")

# 問候 job 每半小時掃一次（cron 0,30 * * * *），故偏好時間必須落在整點或半點——
# 存 07:45 卻在 08:00 問候，是對後台說謊。
#
# public：config.py 用它驗證 PROACTIVE_GREETING_MAX_SHIFT_MINUTES 必須是本值的正倍數
# （非倍數會被 `_align` 吃掉或放大，兩者都是靜默失效——見該處的驗證）。這是「掃描間隔」
# 這件事的唯一真實來源，config 不得自己寫死 30，否則兩份真相會漂移。
SLOT_MINUTES = 30


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
    return round(minute_of_day / SLOT_MINUTES) * SLOT_MINUTES


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
    回 None ⇒ current 已在護軌內（等價的逆否：current 在護軌外 ⇒ 必定回傳非 None）。

    ⚠️ 這是單向蘊含，不是雙向。反例一秒可得：current=(8, 0) 已在護軌內、她十一點才
    活躍 → 回 (8, 30)。故呼叫端**不可**反向讀成「回傳非 None ⇒ 這是護軌拉回」——
    絕大多數的非 None 是正常調整，該照常寫可解釋性欄位（樣本數、中位數、計算時刻）。
    要分辨兩者只能看有沒有足夠樣本，本函式不代為區分。

    ⚠️ 護軌拉回刻意豁免「單次最多調 max_shift_minutes」的幅度上限：拉回是一步到位的
    （current=(5, 0) → (6, 0) 跳 60 分；(0, 0) → (6, 0) 跳 360 分；(23, 0) → (11, 0)
    跳 720 分）。替代方案是每晚只挪 30 分，但把 00:00 的違規設定救回界內要花 12 個
    晚上，這 12 晚她都在違規時間被問候，明顯更糟。稽核「30 分速率限制有被遵守嗎」時
    看到的大跳躍就是這條路徑——那是刻意的豁免，不是失控。
    """
    current_minutes = current[0] * 60 + current[1]

    # 護軌是絕對的，不以「有沒有資料」為條件：現行時間在護軌外就先拉回界內，且刻意
    # 豁免單次幅度上限（一步到位，可能遠大於 max_shift_minutes——理由見 docstring）。
    # 若讓死區先短路，五點就活躍的長輩（diff = 0 落在死區）會被永遠釘死在
    # 違規的五點——而護軌存在的意義，正是為了保護這種長輩。
    # 可達路徑：Task C 已補上 PROACTIVE_GREETING_HOUR 的跨欄位驗證（啟動即失敗），
    # 本層是下游的縱深防禦，兩層都要有：偏好時間也可能來自 DB 裡的舊資料或人工改值。
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


def update_greeting_time(
    elder_id: str,
    *,
    short_term: MemoryStore,
    prefs: GreetingPreferenceStore,
    clock: Callable[[], datetime],
    default_hour: int,
    lookback_days: int,
    min_sample_days: int,
    earliest_hour: int,
    latest_hour: int,
    max_shift_minutes: int,
    lag_tolerance_minutes: int,
) -> None:
    """夜間批次的薄協調函式：讀訊號 → 呼叫純函式 → 存偏好。不經 LLM。

    刻意不設防：讀寫失敗直接往上冒（快速失敗），防線在 worker 的 run_one——
    問候時間算不出來只該是「今晚不調時間」，不該讓值班的人以為整理或摘要壞了。

    回看窗是 [今日零時 − lookback_days 天, 今日零時)，以整天為單位、不含今天：
    批次在凌晨三點多跑，把「今天」算進去等於拿一段註定殘缺的半天當樣本。
    """
    now = clock()
    tz = now.tzinfo
    _, end = previous_day_bounds(now)
    start = end - lookback_days * 86400.0
    first_turns = short_term.first_user_turn_per_day(elder_id, since=start, before=end)
    existing = prefs.get_for_elder(elder_id)
    # 現行值取她自己的偏好；沒有偏好才退回全域設定。拿全域當 current 會讓她每晚被拉回原點。
    current = (existing.hour, existing.minute) if existing else (default_hour, 0)
    nxt = next_greeting_time(
        first_turns=first_turns,
        current=current,
        tz=tz,
        min_sample_days=min_sample_days,
        earliest_hour=earliest_hour,
        latest_hour=latest_hour,
        max_shift_minutes=max_shift_minutes,
        lag_tolerance_minutes=lag_tolerance_minutes,
    )
    if nxt is None:
        return  # 不動就不寫：每晚寫一次 computed_at 會讓後台以為系統一直在調整。

    # ⚠️ 不可無條件呼叫 median_minute_of_day：next_greeting_time 的後置條件
    # 「回 None ⇒ current 在護軌內」是**單向**的，反向不成立。護軌拉回不以樣本數為
    # 條件（護軌若能被「她安靜了一個月」關掉，就不是護軌），故 first_turns=[] 加上
    # 界外的 current 會回傳非 None，而 median([]) 會拋 StatisticsError 炸掉這一步。
    # 此時誠實寫「零天樣本、沒有中位數」，不要編一個假的中位數搪塞可解釋性欄位。
    prefs.save(
        GreetingPreference(
            elder_id=elder_id,
            hour=nxt[0],
            minute=nxt[1],
            computed_at=now.timestamp(),
            sample_days=len(first_turns),
            median_minute_of_day=(
                median_minute_of_day(first_turns, tz) if first_turns else NO_SAMPLE_MEDIAN
            ),
        )
    )
    logger.info(
        "問候時間調整 elder=%s %02d:%02d → %02d:%02d（%d 天樣本）",
        elder_id,
        current[0],
        current[1],
        nxt[0],
        nxt[1],
        len(first_turns),
    )
