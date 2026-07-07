"""build_health_report 的離線測試：時間窗過濾、邊界情況。

這正是原本卡在 route handler、只能經 HTTP 測的組裝邏輯，如今可純函式驗證。
會話主鍵已通道中立：危急事件與提醒皆以 elder_id 直查，不再經 LINE 解析。
"""

from datetime import datetime, timedelta, timezone

from kinsun.reports.health import build_health_report
from kinsun.reports.reminders import ReminderLog
from kinsun.safety.events import RiskEvent
from kinsun.safety.tiers import RiskTier

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=TPE)
RECENT = (NOW - timedelta(days=5)).timestamp()
OLD = (NOW - timedelta(days=40)).timestamp()


class _RiskEvents:
    def __init__(self, by_elder):
        self._by_elder = by_elder

    def list_for_elder(self, elder_id):
        return list(self._by_elder.get(elder_id, []))


class _Reminders:
    def __init__(self, by_elder):
        self._by_elder = by_elder

    def list_for_elder(self, elder_id):
        return list(self._by_elder.get(elder_id, []))


def _risk(created_at, reason="胸悶"):
    return RiskEvent("id", "e1", RiskTier.L2, reason, created_at)


def _reminder(created_at, content="早上用藥"):
    return ReminderLog("id", "e1", "medication", content, created_at)


def _report(*, risk_events, reminder_logs, window_days=30):
    return build_health_report(
        elder_id="e1",
        risk_events=risk_events,
        reminder_logs=reminder_logs,
        now=NOW,
        window_days=window_days,
    )


def test_filters_by_window():
    report = _report(
        risk_events=_RiskEvents({"e1": [_risk(RECENT, "new"), _risk(OLD, "old")]}),
        reminder_logs=_Reminders({"e1": [_reminder(RECENT, "new"), _reminder(OLD, "old")]}),
    )
    assert [r.reason for r in report.risks] == ["new"]
    assert [r.content for r in report.reminders] == ["new"]


def test_empty_when_elder_has_no_data():
    report = _report(
        risk_events=_RiskEvents({"other": [_risk(RECENT)]}),
        reminder_logs=_Reminders({}),
    )
    assert report.risks == []
    assert report.reminders == []


def test_window_days_param_narrows():
    report = _report(
        risk_events=_RiskEvents({"e1": [_risk(RECENT)]}),  # 5 天前
        reminder_logs=_Reminders({}),
        window_days=3,  # 3 天窗 → 濾掉
    )
    assert report.risks == []
