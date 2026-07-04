"""家屬端健康報告：長輩近 N 天的危急事件 ＋ 提醒紀錄彙整。

route handler 只驗身分並出 JSON；組裝（長輩 LINE 解析＋時間窗過濾）在此、可離線測。
與 observability 的管理端活動時間軸（feed／timeline）是不同報告、不同受眾。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from kinsun.accounts.service import AccountService
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
    accounts: AccountService,
    now: datetime,
    window_days: int = 30,
) -> HealthReport:
    """組裝家屬健康報告：抓近 window_days 天的危急事件與提醒，過濾後回結構化報告。

    注意：長輩的 line_user_id 與「發出請求的家屬」是不同的人；此處一律以 elder_id
    解析出的 elder_line_user_id 為準查危急事件，切勿與家屬的 line_user_id 混用。
    """
    cutoff = (now - timedelta(days=window_days)).timestamp()
    elder = accounts.get_elder(elder_id)
    elder_line_user_id = elder.line_user_id if elder else None
    risks = (
        [e for e in risk_events.list_for_line_user(elder_line_user_id) if e.created_at >= cutoff]
        if elder_line_user_id
        else []
    )
    reminders = [r for r in reminder_logs.list_for_elder(elder_id) if r.created_at >= cutoff]
    return HealthReport(risks=risks, reminders=reminders)
