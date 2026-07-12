import { useState } from "react";

import { ElderTimelinePage } from "./ElderTimelinePage";
import { AccountTab } from "./elder-tabs/AccountTab";
import { MemoryTab } from "./elder-tabs/MemoryTab";
import { RemindersTab } from "./elder-tabs/RemindersTab";
import { RiskNotificationsTab } from "./elder-tabs/RiskNotificationsTab";

const TABS = [
  { key: "timeline", label: "時間軸" },
  { key: "reminders", label: "提醒設定" },
  { key: "memory", label: "記憶與摘要" },
  { key: "account", label: "帳號與綁定" },
  { key: "risk", label: "危急通知" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** 長輩詳情（spec 2026-07-12 §3.3）：時間軸之外補四類已落庫但過去看不到的資料。 */
export function ElderDetailPage() {
  const [tab, setTab] = useState<TabKey>("timeline");
  return (
    <section>
      <div className="tab-bar">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={tab === t.key ? "tab tab-active" : "tab"}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "timeline" && <ElderTimelinePage />}
      {tab === "reminders" && <RemindersTab />}
      {tab === "memory" && <MemoryTab />}
      {tab === "account" && <AccountTab />}
      {tab === "risk" && <RiskNotificationsTab />}
    </section>
  );
}
