/**
 * 家屬端底部五項導覽（W5b）。
 *
 * 版面：四個分頁＋**中央凸出的暖黃鍵**。中央那顆不是分頁——它是一個動作，按下去
 * 進「新增提醒」，畫面不會停在一個叫「新增提醒」的空頁上。
 *
 * ⚠️ **每個圖示都有文字標籤**（設計稿明文）。只有圖示的導覽對不熟 App 的家屬等於
 * 一排猜謎，而這個產品的使用者有一半是第一次用這類工具。
 *
 * ⚠️ 無障礙角色分兩種：四個分頁是 `role="tab"`＋`aria-selected`（它們切換的是同一
 * 塊內容），中央那顆是普通 `button`（它導去別的地方）。把動作也標成 tab，讀螢幕的
 * 人會以為按下去會停在那一頁。
 */

import { strings } from "@/strings";

import { BellIcon, HomeIcon, PersonIcon, PlusIcon, ReportIcon } from "./GuardianTabIcons";

export type GuardianTab = "home" | "report" | "notifications" | "profile";

export function GuardianTabBar(props: {
  active: GuardianTab;
  onSelect: (tab: GuardianTab) => void;
  onAdd: () => void;
  /** 未讀通知數，掛在通知分頁上。 */
  unread?: number;
  /** 「我的」那一項顯示目前這位長輩的稱呼，不是寫死的字。 */
  profileLabel: string;
  /** 中央鍵正在處理中（要重打一次 API 才知道帶去哪），期間不可連按。 */
  addBusy?: boolean;
}) {
  const { active, onSelect, onAdd, unread = 0, profileLabel, addBusy = false } = props;

  return (
    <nav
      aria-label={strings.guardianTabs.home}
      className="relative flex shrink-0 items-stretch border-t border-line bg-surface"
      data-testid="guardian-tab-bar"
    >
      <div role="tablist" className="flex flex-1 items-stretch">
        <TabItem
          tab="home"
          active={active}
          onSelect={onSelect}
          label={strings.guardianTabs.home}
          icon={<HomeIcon />}
        />
        <TabItem
          tab="report"
          active={active}
          onSelect={onSelect}
          label={strings.guardianTabs.report}
          icon={<ReportIcon />}
        />

        {/* 中央鍵佔位：它絕對定位凸出於列上方，這個空格是留給它的版面位置。 */}
        <span aria-hidden className="w-[84px] shrink-0" />

        <TabItem
          tab="notifications"
          active={active}
          onSelect={onSelect}
          label={strings.guardianTabs.notifications}
          icon={<BellIcon />}
          badge={unread}
        />
        <TabItem
          tab="profile"
          active={active}
          onSelect={onSelect}
          label={profileLabel}
          icon={<PersonIcon />}
        />
      </div>

      <button
        type="button"
        onClick={onAdd}
        disabled={addBusy}
        aria-label={strings.guardianTabs.addA11y}
        data-testid="guardian-add-action"
        className="absolute left-1/2 top-0 flex size-[62px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-action text-ink shadow-[var(--elevation-action)] transition-[background-color,transform] duration-[var(--motion-press)] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-60 enabled:hover:bg-action-pressed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <PlusIcon size={30} />
      </button>
      <span
        aria-hidden
        className="absolute bottom-1.5 left-1/2 -translate-x-1/2 text-[11px] font-semibold text-ink-soft"
      >
        {strings.guardianTabs.add}
      </span>
    </nav>
  );
}

function TabItem(props: {
  tab: GuardianTab;
  active: GuardianTab;
  onSelect: (tab: GuardianTab) => void;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}) {
  const { tab, active, onSelect, label, icon, badge = 0 } = props;
  const selected = tab === active;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={() => onSelect(tab)}
      // 48px 是所有可點區域的下限；這裡給 60 讓一根手指按得從容。
      className={`relative flex min-h-[60px] flex-1 flex-col items-center justify-center gap-0.5 px-1 pb-1 pt-1.5 text-[11px] font-semibold focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary ${
        selected ? "text-primary" : "text-ink-soft"
      }`}
    >
      {icon}
      <span className="max-w-full truncate">{label}</span>
      {badge > 0 ? (
        <span
          aria-hidden
          className="absolute right-[18%] top-1 flex min-w-5 items-center justify-center rounded-full bg-danger-badge px-1 text-[11px] font-bold leading-4 text-white"
        >
          {badge > 9 ? "9+" : badge}
        </span>
      ) : null}
    </button>
  );
}
