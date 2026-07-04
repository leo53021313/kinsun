"""build_health_report 的離線測試：時間窗過濾、長輩 LINE 解析、邊界情況。

這正是原本卡在 route handler、只能經 HTTP 測的組裝邏輯，如今可純函式驗證。
"""

from datetime import datetime, timedelta, timezone

from kinsun.accounts.models import Elder
from kinsun.accounts.service import AccountService
from kinsun.reports.health import build_health_report
from kinsun.reports.reminders import ReminderLog
from kinsun.safety.events import RiskEvent
from kinsun.safety.tiers import RiskTier
from tests.fakes import FakeAccountStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=TPE)
RECENT = (NOW - timedelta(days=5)).timestamp()
OLD = (NOW - timedelta(days=40)).timestamp()


class _RiskEvents:
    def __init__(self, by_line):
        self._by_line = by_line

    def list_for_line_user(self, line_user_id):
        return list(self._by_line.get(line_user_id, []))


class _Reminders:
    def __init__(self, by_elder):
        self._by_elder = by_elder

    def list_for_elder(self, elder_id):
        return list(self._by_elder.get(elder_id, []))


def _accounts(*elders):
    repo = FakeAccountStore()
    for elder in elders:
        repo.save_elder(elder)
    return AccountService(repo, clock=lambda: NOW)


def _risk(created_at, reason="胸悶"):
    return RiskEvent("id", "U-elder", RiskTier.L2, reason, created_at)


def _reminder(created_at, content="早上用藥"):
    return ReminderLog("id", "e1", "medication", content, created_at)


def _report(*, risk_events, reminder_logs, accounts, window_days=30):
    return build_health_report(
        elder_id="e1",
        risk_events=risk_events,
        reminder_logs=reminder_logs,
        accounts=accounts,
        now=NOW,
        window_days=window_days,
    )


def test_filters_by_window_and_resolves_elder_line():
    report = _report(
        risk_events=_RiskEvents({"U-elder": [_risk(RECENT, "new"), _risk(OLD, "old")]}),
        reminder_logs=_Reminders({"e1": [_reminder(RECENT, "new"), _reminder(OLD, "old")]}),
        accounts=_accounts(Elder("e1", "阿公", "U-elder")),
    )
    assert [r.reason for r in report.risks] == ["new"]
    assert [r.content for r in report.reminders] == ["new"]


def test_no_risks_when_elder_has_no_line_but_reminders_still_by_elder():
    # 長輩未綁 LINE：危急事件無從查（不可誤用家屬 LINE），提醒仍以 elder_id 查得到。
    report = _report(
        risk_events=_RiskEvents({"U-elder": [_risk(RECENT)]}),
        reminder_logs=_Reminders({"e1": [_reminder(RECENT)]}),
        accounts=_accounts(Elder("e1", "阿嬤", None)),
    )
    assert report.risks == []
    assert [r.content for r in report.reminders] == ["早上用藥"]


def test_empty_when_elder_unknown():
    # 查無此長輩：無 LINE 可解析 → 無危急事件（提醒本就以 elder_id 查，這裡也無資料）。
    report = _report(
        risk_events=_RiskEvents({"U-elder": [_risk(RECENT)]}),
        reminder_logs=_Reminders({}),
        accounts=_accounts(),
    )
    assert report.risks == []
    assert report.reminders == []


def test_window_days_param_narrows():
    report = _report(
        risk_events=_RiskEvents({"U-elder": [_risk(RECENT)]}),  # 5 天前
        reminder_logs=_Reminders({}),
        accounts=_accounts(Elder("e1", "阿公", "U-elder")),
        window_days=3,  # 3 天窗 → 濾掉
    )
    assert report.risks == []
