"""自適應問候時間的計算核心。

最重要的一條是 test_the_time_does_not_drift_when_she_only_answers_our_greeting
——它守的是「死區」，那是唯一擋住自我實現漂移的設計。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kinsun.proactive.greeting_time import median_minute_of_day, next_greeting_time

TPE = timezone(timedelta(hours=8))
GUARDS = dict(
    tz=TPE,
    min_sample_days=5,
    earliest_hour=6,
    latest_hour=11,
    max_shift_minutes=30,
    lag_tolerance_minutes=60,
)


def _turns_at(hour: int, minute: int = 0, days: int = 7) -> list[float]:
    """連續 days 天、每天在 hour:minute 各一則。"""
    return [datetime(2026, 7, 1 + d, hour, minute, tzinfo=TPE).timestamp() for d in range(days)]


def test_too_few_samples_means_no_change():
    assert next_greeting_time(first_turns=_turns_at(10, days=4), current=(8, 0), **GUARDS) is None


def test_shifts_later_when_she_wakes_much_later():
    # 八點問候、她通常十一點才第一次講話 → 往後調一格（30 分）
    assert next_greeting_time(first_turns=_turns_at(11), current=(8, 0), **GUARDS) == (8, 30)


def test_shifts_earlier_when_she_is_already_up_before_us():
    # 八點問候、她通常七點就自己來 → 往前調一格
    assert next_greeting_time(first_turns=_turns_at(7), current=(8, 0), **GUARDS) == (7, 30)


def test_inside_the_dead_zone_nothing_moves():
    # 她八點二十活躍、八點問候 → 差 20 分（< 30）→ 不動
    assert next_greeting_time(first_turns=_turns_at(8, 20), current=(8, 0), **GUARDS) is None


def test_the_result_is_clamped_to_the_earliest_hour():
    # 她凌晨四點就活躍（失眠？）→ 也不准把問候排到六點以前
    got = next_greeting_time(first_turns=_turns_at(4), current=(6, 30), **GUARDS)
    assert got == (6, 0)


def test_the_result_is_clamped_to_the_latest_hour():
    got = next_greeting_time(first_turns=_turns_at(15), current=(10, 30), **GUARDS)
    assert got == (11, 0)


def test_the_result_is_aligned_to_the_half_hour():
    # 她通常 10:47 活躍 → 往後調的結果必須落在整點或半點（job 每半小時才跑）
    got = next_greeting_time(first_turns=_turns_at(10, 47), current=(8, 0), **GUARDS)
    assert got is not None
    assert got[1] in (0, 30)


def test_the_median_ignores_the_odd_early_bird_day():
    # 六天十點、一天五點（偶爾早起）→ 中位數仍是十點，不被離群值拉走
    turns = _turns_at(10, days=6) + [datetime(2026, 7, 7, 5, tzinfo=TPE).timestamp()]
    assert median_minute_of_day(turns, TPE) == 10 * 60


def test_the_time_does_not_drift_when_she_only_answers_our_greeting():
    """自我實現漂移的回歸測試——本功能最重要的一條。

    她每天都在被問候後五分鐘才講話（活躍是我們自己觸發的）。若沒有死區，
    她的中位數永遠比現行時間晚五分鐘，時間就逐日往「後」漂到上限十一點
    （突變驗證：拿掉死區，本測試會以「問候時間漂移到 (11, 0)」失敗）。
    有死區就該穩定不動。
    """
    current = (9, 0)
    for _ in range(10):
        turns = [
            datetime(2026, 7, 1 + d, current[0], current[1], tzinfo=TPE).timestamp() + 300
            for d in range(7)
        ]
        nxt = next_greeting_time(first_turns=turns, current=current, **GUARDS)
        if nxt is None:
            break
        current = nxt
    assert current == (9, 0), f"問候時間漂移到 {current}"


def test_it_converges_and_then_stops_when_she_wakes_late():
    """八點問候、她十一點活躍：逐日往後，最後停在容忍度邊緣，不會無限往後。

    收斂點是 10:00 而非她的中位數 11:00——|11:00 − 10:00| = 60 就進入往後的死區
    （lag_tolerance_minutes）。這是刻意的保守：真的睡到十一點的長輩會被跟上到
    十點，而「其實七點就醒、只是一小時後才看手機」的長輩不會被推著跑。
    """
    current = (8, 0)
    seen = []
    for _ in range(20):
        nxt = next_greeting_time(first_turns=_turns_at(11), current=current, **GUARDS)
        if nxt is None:
            break
        assert nxt != current, "回傳了與現值相同的時間，應該回 None"
        current = nxt
        seen.append(current)
    assert current == (10, 0), f"收斂在 {current}"
    assert len(seen) == 4  # 8:00 → 10:00，一次 30 分


# --- 以下為 Task D 實作時補上的邊界情境（見報告） ---


def _iterate_to_fixpoint(turns: list[float], current: tuple[int, int], **guards) -> tuple[int, int]:
    """反覆套用 next_greeting_time 直到回 None，回傳收斂點。

    若 40 次仍不收斂就視為失控（正常收斂最多 (11-6)*60/30 = 10 步）。
    """
    for _ in range(40):
        nxt = next_greeting_time(first_turns=turns, current=current, **guards)
        if nxt is None:
            return current
        assert nxt != current, f"回傳了與現值相同的時間 {nxt}，應該回 None"
        current = nxt
    raise AssertionError(f"未收斂，停在 {current}")


def test_it_converges_and_then_stops_when_she_is_up_early():
    """往前的方向也要收斂——簡報只測了往後。

    收斂點是「她的中位數 ∓ 死區寬度」，不是她的中位數本身：她七點自己來，
    問候停在 07:30 而非 07:00。簡報的 docstring 原本寫 07:00，與實作不符，
    已一併更正（見報告）。
    """
    settled = _iterate_to_fixpoint(_turns_at(7), (8, 0), **GUARDS)
    assert settled == (7, 30), f"收斂在 {settled}"


def test_no_samples_at_all_means_no_change():
    """完全沒有資料時要回 None，而不是讓 median([]) 炸掉整個夜間批次。

    min_sample_days 由 Task C 驗證 ≥1，但本函式是純函式、不讀 Settings，
    不能假設呼叫端一定傳合法值。
    """
    assert next_greeting_time(first_turns=[], current=(8, 0), **GUARDS) is None
    lenient = {**GUARDS, "min_sample_days": 0}
    assert next_greeting_time(first_turns=[], current=(8, 0), **lenient) is None


def test_a_current_time_outside_the_guardrails_is_pulled_back():
    """現行時間在護軌外時要拉回界內——即使她的活躍時刻就在那個違規時間上。

    可達路徑：PROACTIVE_GREETING_HOUR 沒有被 Task C 的跨欄位驗證涵蓋，
    設成 5 而下限是 6 時，Task E 拿它當 current 就會踩到。

    這是死區的反面陷阱：她真的五點就活躍（失眠），diff = 0 落在死區，
    若讓死區先短路，問候就永遠釘死在違規的五點——而護軌存在的意義，
    正是為了保護這種長輩。
    """
    # 她五點活躍、現行也是五點 → 差 0 分，死區會說「不用動」，但護軌說「不准」
    assert next_greeting_time(first_turns=_turns_at(5), current=(5, 0), **GUARDS) == (6, 0)
    # 上限側對稱：她十二點活躍、現行十二點
    assert next_greeting_time(first_turns=_turns_at(12), current=(12, 0), **GUARDS) == (11, 0)
    # 樣本不足也照拉：護軌是絕對的，不以「有沒有資料」為條件
    assert next_greeting_time(first_turns=[], current=(5, 0), **GUARDS) == (6, 0)


def test_it_stays_put_once_it_reaches_a_guardrail():
    """已經站在護軌上、她還要更早／更晚 → 回 None，不是每晚回同一個值。

    守的是「無處可去時不要謊報有變動」，否則 Task E 會每晚寫一次無意義的
    computed_at，後台看起來像系統一直在調整。
    """
    assert next_greeting_time(first_turns=_turns_at(15), current=(11, 0), **GUARDS) is None
    assert next_greeting_time(first_turns=_turns_at(3), current=(6, 0), **GUARDS) is None


def test_every_result_is_a_valid_wall_clock_time_inside_the_guardrails():
    """夾取不會靜默繞回：掃過各種極端 target／current，結果永遠是合法時刻。

    若夾取改用模運算或 timedelta，hour=25 會靜默變成隔天一點（惡夢情境）；
    純整數 max／min 夾進 [earliest*60, latest*60] 後才 divmod，繞回不可能發生。

    順帶釘死本函式的後置條件：回 None ⇔ 現行時間已在護軌內。
    """
    earliest, latest = GUARDS["earliest_hour"], GUARDS["latest_hour"]
    for target_hour in range(0, 24):
        for current_hour in range(0, 24):
            for current_minute in (0, 30, 47):
                current = (current_hour, current_minute)
                got = next_greeting_time(
                    first_turns=_turns_at(target_hour), current=current, **GUARDS
                )
                if got is None:
                    cm = current_hour * 60 + current_minute
                    assert earliest * 60 <= cm <= latest * 60, f"{current} 在護軌外卻回 None"
                    continue
                hour, minute = got
                assert 0 <= hour <= 23, f"{current}→{got} 小時繞回"
                assert 0 <= minute <= 59, f"{current}→{got} 分鐘越界"
                assert earliest <= hour <= latest, f"{current}→{got} 逃出護軌"
                assert not (hour == latest and minute > 0), f"{current}→{got} 超過上限"


def test_extreme_outliers_do_not_move_the_median():
    """兩側各一天極端值（凌晨三點失眠、半夜十一點）→ 中位數仍是十點。

    守的是「用中位數不用平均數」：平均數會被拉到 (5*600+180+1380)/7 ≈ 651（10:51）。
    """
    turns = (
        _turns_at(10, days=5)
        + [datetime(2026, 7, 6, 3, tzinfo=TPE).timestamp()]
        + [datetime(2026, 7, 7, 23, tzinfo=TPE).timestamp()]
    )
    assert median_minute_of_day(turns, TPE) == 10 * 60


def test_activity_spanning_midnight_still_converges_inside_the_guardrails():
    """她的活躍時刻橫跨午夜（23:50 與 00:10 交錯）→ 中位數在數學上失去意義。

    minute_of_day 是線性座標、不是環狀座標，跨午夜的中位數會落到荒謬的位置
    （偶數筆時甚至是中午）。這是已知限制。本測試守的不是「算得準」，而是
    「算不準時也不會失控」：護軌仍把結果關在界內，且迭代必定收斂。
    """
    turns = [
        datetime(2026, 7, 1 + d, 23, 50, tzinfo=TPE).timestamp()
        if d % 2
        else datetime(2026, 7, 1 + d, 0, 10, tzinfo=TPE).timestamp()
        for d in range(8)
    ]
    settled = _iterate_to_fixpoint(turns, (8, 0), **GUARDS)
    assert GUARDS["earliest_hour"] <= settled[0] <= GUARDS["latest_hour"]


def test_a_max_shift_wider_than_the_whole_guardrail_band_does_not_overshoot():
    """max_shift（600 分）遠大於整條護軌區間（6:00–11:00 只有 300 分）。

    守的是「步伐大於區間時不會一步跨出護軌」：夾取在對齊之後才做，
    所以 8:00 + 600 分 = 18:00 會被關回 11:00，而不是變成合法外的時刻。
    """
    # 容忍度跟著放大：Task C 驗證 lag_tolerance ≥ max_shift，這裡不做出設定擋掉的組合。
    guards = {**GUARDS, "max_shift_minutes": 600, "lag_tolerance_minutes": 600}
    got = next_greeting_time(first_turns=_turns_at(23), current=(6, 0), **guards)
    assert got == (11, 0)
    settled = _iterate_to_fixpoint(_turns_at(23), (6, 0), **guards)
    assert settled == (11, 0)


def _settle_with_response_lag(
    lag_minutes: int, current: tuple[int, int], **guards
) -> tuple[int, int]:
    """模擬「她固定在問候後 lag_minutes 分鐘才回話」，反覆推算直到收斂。

    這是自我實現迴圈的模型：她的活躍時刻永遠是「現行問候時間 ＋ 固定延遲」，
    因為她的活躍根本是被我們的問候觸發的。
    """
    for _ in range(40):
        turns = [
            datetime(2026, 7, 1 + d, current[0], current[1], tzinfo=TPE).timestamp()
            + lag_minutes * 60
            for d in range(7)
        ]
        nxt = next_greeting_time(first_turns=turns, current=current, **guards)
        if nxt is None:
            return current
        current = nxt
    raise AssertionError(f"未收斂，停在 {current}")


def test_a_forty_five_minute_response_lag_no_longer_drifts():
    """她八點收到問候、四十五分鐘後才看手機（手機放在別的房間）→ 時間必須不動。

    這是本次修正的核心，也是回歸護欄。舊行為：45 分 > 往前的死區 30 分 → 判定
    太早 → 往後調 → 她還是 45 分後才看 → 再往後 → 一路推到上限 11:00。結果是
    「十一點問候、十一點四十五她才回」，比原本「八點問候、八點四十五回」更糟，
    而且「早安」變成將近中午。

    修法是把往後調的容忍度（lag_tolerance_minutes＝60）與往前的死區
    （max_shift_minutes＝30）拆開，因為兩個方向的訊號品質根本不同：
    「問候後才有動靜」分不出「還沒醒」與「只是慢慢看手機」。

    突變驗證：把 lag_tolerance_minutes 換回 max_shift_minutes（30），本測試會以
    「問候時間漂移到 (11, 0)」失敗。
    """
    settled = _settle_with_response_lag(45, (8, 0), **GUARDS)
    assert settled == (8, 0), f"問候時間漂移到 {settled}"


def test_a_response_lag_longer_than_the_tolerance_still_shifts_later():
    """容忍度不是「往後永不調整」：延遲 90 分（> 60）仍要往後調一格。

    守的是「別把死區開得太大而讓機制失效」——真的睡得晚的長輩仍要被跟上。
    """
    # 八點問候、她通常九點半才第一次講話 → 差 90 分 > 容忍度 60 → 往後調 30 分
    assert next_greeting_time(first_turns=_turns_at(9, 30), current=(8, 0), **GUARDS) == (8, 30)


def test_the_dead_zone_for_shifting_earlier_is_still_max_shift():
    """往前的死區不受容忍度影響，仍是 max_shift_minutes（30 分）。

    「她在問候之前就自己來了」是乾淨訊號：問候還沒發出，不可能是我們觸發的，
    她確實醒著。故往前調不需要往後調那種保守。若誤把 lag_tolerance（60）也套在
    往前的方向，第二條斷言會回 None 而失敗。
    """
    # 她七點四十活躍、八點問候 → 早 20 分（< 30）→ 不動
    assert next_greeting_time(first_turns=_turns_at(7, 40), current=(8, 0), **GUARDS) is None
    # 她七點十五活躍 → 早 45 分（> 30，但 < 容忍度 60）→ 仍要往前調
    assert next_greeting_time(first_turns=_turns_at(7, 15), current=(8, 0), **GUARDS) == (7, 30)


def test_a_response_lag_far_longer_than_the_tolerance_drifts_but_the_guardrail_stops_it():
    """殘留限制：她固定在問候後 90 分（> 容忍度 60）才回話 → 仍會自我實現漂移。

    容忍度只把自我實現迴圈的門檻從 30 分抬到 60 分，沒有根治它：延遲更長時時間
    仍會逐日往後推，最後被上限 11:00 接住。守的是「容忍度失效時護軌是最後一道
    防線」，並誠實記錄這個限制（見報告：要根治得比對問候實際送出的時刻，而
    first_user_turn_per_day 這個訊號沒有那個資訊）。
    """
    settled = _settle_with_response_lag(90, (8, 0), **GUARDS)
    assert settled == (11, 0), f"應被上限接住，卻停在 {settled}"
