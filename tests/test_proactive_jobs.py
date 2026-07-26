from datetime import datetime, timedelta, timezone

from kinsun.cron.registry import GREETING_SCAN_CRON
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
        cron=GREETING_SCAN_CRON,
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
        cron="0 10 * * *",
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
        cron="0 10 * * *",
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


# --- 問候 intent 的話題新聞改為工具引導（D-74 消費端，2026-07-25：push→pull）---


def test_greeting_intent_guides_model_to_use_get_news_tool():
    from kinsun.proactive.jobs import GREETING_INTENT, greeting_intent

    intent = greeting_intent(datetime(2026, 7, 17, 8, 0, tzinfo=TPE))
    assert intent.startswith(GREETING_INTENT)
    assert "get_news" in intent
    assert "topic" in intent


def test_greeting_intent_no_longer_weaves_headlines_directly():
    # push→pull：intent 不再直接夾帶標題（「最近的新聞有 …」句型走入歷史），
    # 素材改由模型在工具迴圈中自行拉取。
    from kinsun.proactive.jobs import greeting_intent

    intent = greeting_intent(datetime(2026, 7, 17, 8, 0, tzinfo=TPE))
    assert "最近的新聞有" not in intent


# --- 問候 intent 織入興趣提示（Leo 2026-07-25 核可：興趣驅動挑題）---


def test_greeting_intent_weaves_interest_hints():
    from kinsun.proactive.jobs import greeting_intent

    intent = greeting_intent(
        datetime(2026, 7, 17, 8, 0, tzinfo=TPE), interests=("喜歡園藝", "常去公園健走")
    )
    assert "喜歡園藝" in intent
    assert "常去公園健走" in intent
    assert "topic" in intent  # 指示模型拿興趣當 get_news 的 topic


def test_greeting_intent_without_interests_has_no_interest_section():
    from kinsun.proactive.jobs import greeting_intent

    intent = greeting_intent(datetime(2026, 7, 17, 8, 0, tzinfo=TPE))
    assert "興趣可能包含" not in intent


def test_greeting_intent_caps_interests_at_three():
    from kinsun.proactive.jobs import greeting_intent

    intent = greeting_intent(
        datetime(2026, 7, 17, 8, 0, tzinfo=TPE),
        interests=("一", "二", "三", "第四筆不該出現"),
    )
    assert "第四筆不該出現" not in intent


# --- 補問候的時限（2026-07-26 全流程模擬實測：排程停擺一天後在夜裡重啟）---


def test_it_does_not_greet_at_night_after_a_whole_day_of_downtime():
    """⚠️ 這是實測踩到的傷害：排程器停擺整天，晚上九點半重新啟動。

    「已過她的時間且今天沒問候過」這條規則，會對當天所有沒被問候的長輩送出
    一句「早安」——正式環境當時有 64 位長輩。一句遲到十三小時的早安比沒有更糟。
    """
    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"],
        greet_one=greeted.append,
        prefs=_prefs_at("e1", 8, 0),
        at=(21, 30),
    ).run()
    assert greeted == []


def test_a_morning_restart_still_catches_up():
    """時限不可以把既有的補問候能力關掉：上午恢復服務照樣補得到。"""
    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"],
        greet_one=greeted.append,
        prefs=_prefs_at("e1", 8, 0),
        at=(11, 45),
    ).run()
    assert greeted == ["e1"]


def test_the_delay_limit_is_measured_from_her_own_time_not_the_clock():
    """時限是相對她自己的時間算的：偏好 6:00 的長輩在 10:30 已經超過四小時。"""
    greeted = []
    _greeting_job(
        sessions=lambda: ["e1"],
        greet_one=greeted.append,
        prefs=_prefs_at("e1", 6, 0),
        at=(10, 30),
    ).run()
    assert greeted == []


def test_inactivity_care_is_not_pushed_at_night_after_downtime():
    """⚠️ 同一個實測情境：排在早上十點的關懷，補跑時不可以在夜裡送出去。"""
    cared = []
    night = NOW.replace(hour=21, minute=30)
    build_inactivity_job(
        sessions=lambda: ["u1"],
        last_active=lambda _s: (NOW - timedelta(days=3)).timestamp(),
        clock=lambda: night,
        threshold_seconds=2 * 86400,
        care_one=cared.append,
        cron="0 10 * * *",
    ).run()
    assert cared == []


def test_inactivity_care_still_goes_out_during_the_day():
    """白天恢復服務照樣關心得到——安靜時段擋的是夜裡，不是「晚了」。"""
    cared = []
    noon = NOW.replace(hour=13, minute=0)
    build_inactivity_job(
        sessions=lambda: ["u1"],
        last_active=lambda _s: (NOW - timedelta(days=3)).timestamp(),
        clock=lambda: noon,
        threshold_seconds=2 * 86400,
        care_one=cared.append,
        cron="0 10 * * *",
    ).run()
    assert cared == ["u1"]


def test_inactivity_care_survives_midnight():
    """⚠️ 跨午夜的坑：早期寫法拿時分做減法，凌晨 01:30 減 10:00 得到 -570，
    小於任何上限都會被判成「還在時限內」→ 長輩凌晨收到「我很想你」。
    夜間重啟正是最常見的重啟時段，這一格才是護欄最該擋住的。
    """
    cared = []
    after_midnight = (NOW + timedelta(days=1)).replace(hour=1, minute=30)
    build_inactivity_job(
        sessions=lambda: ["u1"],
        last_active=lambda _s: (NOW - timedelta(days=3)).timestamp(),
        clock=lambda: after_midnight,
        threshold_seconds=2 * 86400,
        care_one=cared.append,
        cron="0 10 * * *",
    ).run()
    assert cared == []
