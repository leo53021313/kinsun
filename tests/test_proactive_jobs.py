from datetime import datetime, timedelta, timezone

from kinsun.proactive.jobs import build_greeting_job, build_inactivity_job
from kinsun.proactive.preferences import FakeGreetingPreferenceStore, GreetingPreference

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 6, 29, 10, 0, tzinfo=TPE)


_DEFAULT_PREFS = object()  # 與 prefs=None（緊急關閉開關）區分開來


def _greeting_job(
    *,
    sessions,
    greet_one,
    prefs=_DEFAULT_PREFS,
    greeted_today=lambda _e: False,
    at=(9, 0),
    default_hour=8,
):
    """問候 job 的預設接線；每條測試只覆寫自己在乎的那一項。

    at 預設 09:00（晚於 default_hour 08:00），故「時間到了沒」不會意外成為
    測試失敗的原因——想測時間閘門的測試自己指定 at。
    """
    return build_greeting_job(
        sessions=sessions,
        greet_one=greet_one,
        default_hour=default_hour,
        prefs=FakeGreetingPreferenceStore() if prefs is _DEFAULT_PREFS else prefs,
        greeted_today=greeted_today,
        clock=lambda: datetime(2026, 7, 16, at[0], at[1], tzinfo=TPE),
    )


def _prefs_at(elder_id: str, hour: int, minute: int) -> FakeGreetingPreferenceStore:
    prefs = FakeGreetingPreferenceStore()
    prefs.save(
        GreetingPreference(
            elder_id=elder_id,
            hour=hour,
            minute=minute,
            computed_at=0.0,
            sample_days=7,
            median_minute_of_day=hour * 60 + minute,
        )
    )
    return prefs


def test_greeting_runs_for_each_session():
    greeted = []
    job = _greeting_job(sessions=lambda: ["u1", "u2"], greet_one=greeted.append)
    job.run()
    assert greeted == ["u1", "u2"]
    assert job.name == "daily-greeting"


def test_greeting_isolates_failure():
    greeted = []

    def greet_one(s):
        if s == "u1":
            raise RuntimeError("boom")
        greeted.append(s)

    _greeting_job(sessions=lambda: ["u1", "u2"], greet_one=greet_one).run()
    assert greeted == ["u2"]


def test_the_greeting_job_scans_every_half_hour():
    """每位長輩的問候時間對齊半點（spec 2026-07-16），故掃描頻率必須是半小時。"""
    job = _greeting_job(sessions=lambda: [], greet_one=lambda _e: None)
    assert job.cron == "0,30 * * * *"


def test_it_greets_once_her_preferred_time_has_passed():
    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"],
        greet_one=greeted.append,
        prefs=_prefs_at("e1", 9, 30),
        at=(9, 30),
    ).run()
    assert greeted == ["e1"]


def test_it_stays_quiet_before_her_preferred_time():
    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"],
        greet_one=greeted.append,
        prefs=_prefs_at("e1", 9, 30),
        at=(9, 0),
    ).run()
    assert greeted == []


def test_her_preference_overrides_the_global_hour_in_both_directions():
    """偏好比全域設定晚 → 全域時間到了也不能問候；偏好比全域早 → 提早問候。

    守的是「default_hour 只是沒有偏好時的退路」，不是下限也不是上限。
    """
    late, early = [], []
    _greeting_job(
        sessions=lambda: ["e1"], greet_one=late.append, prefs=_prefs_at("e1", 10, 0), at=(8, 0)
    ).run()
    assert late == []  # 全域 08:00 到了，但她的偏好是 10:00
    _greeting_job(
        sessions=lambda: ["e1"], greet_one=early.append, prefs=_prefs_at("e1", 6, 30), at=(6, 30)
    ).run()
    assert early == ["e1"]  # 全域 08:00 還沒到，但她的偏好是 06:30


def test_it_does_not_greet_twice_in_one_day():
    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"],
        greet_one=greeted.append,
        prefs=_prefs_at("e1", 8, 0),
        greeted_today=lambda _e: True,
        at=(10, 0),
    ).run()
    assert greeted == []


def test_it_still_greets_late_when_her_slot_was_missed():
    """worker 半夜當機、早上才恢復：她的時段早就過了，仍要補問候（晚一點，但有）。

    這是「已過＋今天沒問候過」而非「精確比對時段」的理由——Scheduler 的補跨語意
    只會補跑一次，精確比對會讓該時段的長輩整天被漏掉。
    """
    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"],
        greet_one=greeted.append,
        prefs=_prefs_at("e1", 8, 0),
        at=(10, 30),
    ).run()
    assert greeted == ["e1"]


def test_an_elder_without_a_preference_falls_back_to_the_global_hour():
    greeted = []
    _greeting_job(
        sessions=lambda: ["newbie"],
        greet_one=greeted.append,
        prefs=FakeGreetingPreferenceStore(),
        at=(8, 0),
    ).run()
    assert greeted == ["newbie"]


def test_a_failure_to_check_today_skips_that_elder_rather_than_double_greeting():
    def explode(_elder_id: str) -> bool:
        raise RuntimeError("db down")

    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"],
        greet_one=greeted.append,
        prefs=_prefs_at("e1", 8, 0),
        greeted_today=explode,
        at=(9, 0),
    ).run()  # 不應拋出
    assert greeted == []  # 寧可漏問候，不可重複轟炸


def test_a_failure_to_read_preferences_falls_back_to_the_global_hour():
    """偏好讀取失敗 ＝ 退回本功能之前的行為（全體 PROACTIVE_GREETING_HOUR），不是靜默停擺。

    若改成跳過該長輩，greeting_preferences 持續失敗（權限、壞遷移）時就沒有人會
    被問候；退回全域時間則是「降級但照常運作」，且每位長輩每次掃描都留一筆 warning。
    代價：偏好晚於全域的長輩會在故障期間被早問候一次——已知取捨。
    """

    class _Exploding(FakeGreetingPreferenceStore):
        def get_for_elder(self, elder_id):
            raise RuntimeError("db down")

    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"], greet_one=greeted.append, prefs=_Exploding(), at=(8, 0)
    ).run()
    assert greeted == ["e1"]


def test_prefs_none_means_the_global_hour_for_everyone():
    """緊急關閉開關（PROACTIVE_GREETING_ADAPTIVE_ENABLED=false）的下游語意：
    prefs=None ＝ 一列偏好都不讀，全體回退全域時間。"""
    greeted = []
    _greeting_job(sessions=lambda: ["e1"], greet_one=greeted.append, prefs=None, at=(8, 0)).run()
    assert greeted == ["e1"]


def test_inactivity_only_cares_for_stale():
    cared = []
    last = {
        "u1": (NOW - timedelta(days=3)).timestamp(),  # 失聯
        "u2": (NOW - timedelta(hours=1)).timestamp(),  # 新近
        "u3": None,  # 從未發話 → 跳過
    }
    job = build_inactivity_job(
        sessions=lambda: ["u1", "u2", "u3"],
        last_active=lambda s: last[s],
        clock=lambda: NOW,
        threshold_seconds=2 * 86400,
        care_one=cared.append,
        hour=10,
    )
    job.run()
    assert cared == ["u1"]


def test_inactivity_isolates_failure():
    cared = []

    def care_one(s):
        if s == "u1":
            raise RuntimeError("boom")
        cared.append(s)

    old = (NOW - timedelta(days=5)).timestamp()
    build_inactivity_job(
        sessions=lambda: ["u1", "u2"],
        last_active=lambda s: old,
        clock=lambda: NOW,
        threshold_seconds=2 * 86400,
        care_one=care_one,
        hour=10,
    ).run()
    assert cared == ["u2"]


# --- 問候 intent 織入日期（2026-07-17：固定 intent 讓開場白 4 次 3 次逐字相同）---


def test_greeting_intent_weaves_date_and_weekday():
    from kinsun.proactive.jobs import GREETING_INTENT, greeting_intent

    intent = greeting_intent(datetime(2026, 7, 17, 8, 0, tzinfo=TPE))  # 星期五
    assert GREETING_INTENT in intent
    assert "7" in intent and "17" in intent and "星期五" in intent


def test_greeting_intent_differs_by_day():
    from kinsun.proactive.jobs import greeting_intent

    a = greeting_intent(datetime(2026, 7, 17, 8, 0, tzinfo=TPE))
    b = greeting_intent(datetime(2026, 7, 18, 8, 0, tzinfo=TPE))
    assert a != b
