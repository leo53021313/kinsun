"""家屬端健康報告：長輩近 N 天的危急事件 ＋ 提醒紀錄彙整。

route handler 只驗身分並出 JSON；組裝（時間窗過濾）在此、可離線測。
與 observability 的管理端活動時間軸（feed／timeline）是不同報告、不同受眾。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from kinsun.reports.reminders import ReminderLog, ReminderLogStore
from kinsun.safety.events import RiskEvent, RiskEventStore


@dataclass(frozen=True)
class HealthReport:
    risks: list[RiskEvent]
    reminders: list[ReminderLog]


def build_health_report(
    *,
    elder_id: str,
    risk_events: RiskEventStore,
    reminder_logs: ReminderLogStore,
    now: datetime,
    window_days: int = 30,
) -> HealthReport:
    """組裝家屬健康報告：抓近 window_days 天的危急事件與提醒，過濾後回結構化報告。

    危急事件與提醒皆以 elder_id 為鍵直查（會話主鍵已通道中立，不再經 LINE 解析）。
    """
    cutoff = (now - timedelta(days=window_days)).timestamp()
    risks = [e for e in risk_events.list_for_elder(elder_id) if e.created_at >= cutoff]
    reminders = [r for r in reminder_logs.list_for_elder(elder_id) if r.created_at >= cutoff]
    return HealthReport(risks=risks, reminders=reminders)
