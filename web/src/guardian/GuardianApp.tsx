/**
 * 家屬端在手機外框內部的導覽（W5b：五項 Tabs）。
 *
 * ## 兩層導覽，不是一層
 *
 * - **分頁**（首頁／報告／通知／我的）切換的是同一塊內容，底部導覽列常駐。
 * - **深層頁**（長輩詳情、行程管理）push 在分頁殼**之上**，此時導覽列消失——它們
 *   不是分頁的同級選項，留著導覽列會讓人以為隨時可以橫向跳走。
 * - **認證畫面**（登入／註冊）在殼之外，未登入時不該看到導覽列。
 *
 * 兩層共用同一個 `useScreenStack`：堆疊深度 1＝分頁殼，深度 >1＝深層頁。分成兩套
 * 狀態的話，「從詳情返回要回到原本那個分頁」就得自己記，而那正是最容易漏掉的一條。
 *
 * ⚠️ 畫面切換是元件狀態、不進瀏覽器網址列（見 nav/useScreenStack 的說明）。
 * ⚠️ 未登入時一律強制回到登入畫面：session 被 401 清掉之後，若還停在長輩詳情頁，
 *    畫面會停在最後一次成功的資料上，讓人以為還連得上。
 */

import { useCallback, useEffect, useState } from "react";

import type { Elder } from "kinsun-shared/types";

import { useScreenStack } from "@/nav/useScreenStack";
import { GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";
import { ErrorText } from "@/ui/Feedback";

import { DailySummaryScreen } from "./DailySummaryScreen";
import { EditAppointmentScreen } from "./EditAppointmentScreen";
import { ElderDetailScreen } from "./ElderDetailScreen";
import { GuardianTabBar, type GuardianTab } from "./GuardianTabBar";
import { GuardianTabsProvider } from "./GuardianTabsProvider";
import { HomeScreen } from "./HomeScreen";
import { LoginScreen } from "./LoginScreen";
import { NotificationsScreen } from "./NotificationsScreen";
import { ProfileScreen } from "./ProfileScreen";
import { RegisterScreen } from "./RegisterScreen";
import { ReportScreen } from "./ReportScreen";
import { SchedulesScreen } from "./SchedulesScreen";
import { primaryElderLabel, useGuardianTabsState } from "./guardianTabsContext";

export type GuardianRoute =
  | { name: "login" }
  | { name: "register" }
  /** 分頁殼。哪一個分頁在前面由 `activeTab` 決定，不進堆疊——分頁之間是平行的。 */
  | { name: "tabs" }
  // persona 跟著一起帶（2026-08-05）：詳情頁的個性選擇器要知道目前是哪一種，
  // 才不會每次進去都預選第一個。與 elderName 同一條路。
  | { name: "elder"; elderId: string; elderName: string; persona: string }
  // elderName 跟著一起帶：家屬管兩位以上長輩時，行程管理頁若只有「行程管理」
  // 四個字，畫面上沒有任何字告訴他正在編誰的提醒。
  | { name: "schedules"; elderId: string; elderName: string }
  /** 每日摘要獨立畫面（W6）：切日與分享。 */
  | { name: "summary"; elderId: string; elderName: string }
  /** 改回診時間（W6）。回診有自己的畫面，其餘類型仍在行程管理頁原地編輯。 */
  | { name: "editAppointment"; elderId: string; scheduleId: string };

type GuardianAppProps = {
  /**
   * 把家屬產生的綁定碼直接送到長輩欄（spec W-15 內測捷徑）。轉交給
   * `HomeScreen`／`ElderDetailScreen`，接線見 `stage/StagePage.tsx`——
   * `GuardianApp` 自己不需要知道長輩欄的任何事，只單純往下傳。
   */
  onSendCodeToElder?: (code: string) => void;
  /** 通知未讀數（P4 Task 4，見 `stage/StagePage.tsx` 的 `guardianFeed.unread`）。 */
  unread?: number;
};

export function GuardianApp(props: GuardianAppProps) {
  // Provider 一律掛著（未登入時它自己不打 API，見該檔的守門）：條件掛載會讓
  // 登入成功那一刻整棵子樹重掛，剛載好的長輩又被丟掉重讀一次。
  return (
    <GuardianTabsProvider>
      <GuardianAppBody {...props} />
    </GuardianTabsProvider>
  );
}

function GuardianAppBody(props: GuardianAppProps) {
  const { onSendCodeToElder, unread } = props;
  const { session } = GuardianSession.useSession();
  const stack = useScreenStack<GuardianRoute>(session ? { name: "tabs" } : { name: "login" });
  const { reset, push } = stack;
  const { primaryElder, refreshPrimaryElder } = useGuardianTabsState();

  const [activeTab, setActiveTab] = useState<GuardianTab>("home");
  const [addBusy, setAddBusy] = useState(false);
  const [addError, setAddError] = useState("");

  // 登入狀態消失（登出或 401）就回到登入畫面。留在原畫面的話，上面會停著最後
  // 一次成功載入的資料，看起來像還連得上。
  //
  // ⚠️ 依賴陣列只放 [loggedIn, reset]，刻意不放路由狀態：這個 effect 要在
  // 「登入狀態改變」時才觸發，不是「每次換畫面」都觸發。試過把目前路由名稱
  // 加進依賴陣列以避免首次掛載時多一次無謂的 reset，結果實際跑測試才發現
  // 那樣會讓「還沒登入時 push 去 register」也算進這個 effect 的觸發時機
  // ——一登入頁 push 到 register，登入狀態沒變但路由變了，effect 照樣被
  // 判定要跑，`!loggedIn` 仍是 true，於是立刻把使用者退回登入頁，切不進註
  // 冊頁。這個「省一次 re-render」的最佳化划不來，維持原樣。
  const loggedIn = session !== null;
  useEffect(() => {
    if (!loggedIn) {
      reset({ name: "login" });
    }
  }, [loggedIn, reset]);

  // 登出時把分頁狀態一起歸零：上一個帳號停在「我的」，換人登入會直接看到別人
  // 長輩的稱呼。
  //
  // ⚠️ 用「render 期間調整 state」而不是塞進上面那個 effect：`setActiveTab` 是純粹
  // 的狀態調整，放進 effect 會多跑一次 commit（eslint 的
  // `react-hooks/set-state-in-effect` 擋的就是它）。上面那個 effect 留著是因為
  // `reset` 動的是導覽堆疊，不是這一層的 state。
  const [previousLoggedIn, setPreviousLoggedIn] = useState(loggedIn);
  if (previousLoggedIn !== loggedIn) {
    setPreviousLoggedIn(loggedIn);
    if (!loggedIn) {
      setActiveTab("home");
      setAddError("");
    }
  }

  const openElder = useCallback(
    (elder: Elder) =>
      push({
        name: "elder",
        elderId: elder.elder_id,
        elderName: elder.nickname?.trim() || elder.name,
        persona: elder.persona,
      }),
    [push],
  );

  /**
   * 中央黃鍵：進「新增提醒」。
   *
   * ⚠️ **按下當刻重打一次 API，不讀 context 快取**（與 App 同一個理由）：家屬剛在
   * 首頁建完第一位長輩，快取可能還是空的，讀快取會把他丟回首頁說「還沒有長輩」。
   *
   * ⚠️ 目的地是行程管理頁——那裡才有新增區塊。設計文件寫的是「新增提醒流程」，
   * 但兩端的實作都是這一頁，不要被文件的措辭帶去找一個不存在的畫面。
   */
  const openAddReminder = useCallback(async () => {
    if (addBusy) return;
    setAddBusy(true);
    setAddError("");
    try {
      const result = await refreshPrimaryElder();
      if (result.error) {
        // 不靜默失敗：按了沒反應會讓家屬一直按。
        setAddError(result.error);
        return;
      }
      if (!result.elder) {
        // 還沒有長輩就先去建立——首頁才有那個表單。
        setActiveTab("home");
        setAddError(strings.guardianHome.empty);
        return;
      }
      push({
        name: "schedules",
        elderId: result.elder.elder_id,
        elderName: result.elder.nickname?.trim() || result.elder.name,
      });
    } finally {
      setAddBusy(false);
    }
  }, [addBusy, push, refreshPrimaryElder]);

  function renderTab() {
    switch (activeTab) {
      case "home":
        return (
          <HomeScreen
            onOpenElder={(elderId, elderName, persona) =>
              push({ name: "elder", elderId, elderName, persona })
            }
            onOpenNotifications={() => setActiveTab("notifications")}
            onSendCodeToElder={onSendCodeToElder}
            unread={unread}
          />
        );
      case "report":
        return <ReportScreen onOpenElder={openElder} onAddElder={() => setActiveTab("home")} />;
      case "notifications":
        return <NotificationsScreen />;
      case "profile":
        return <ProfileScreen onOpenElder={openElder} onAddElder={() => setActiveTab("home")} />;
      default: {
        const unreachable: never = activeTab;
        throw new Error(`未接線的家屬端分頁：${JSON.stringify(unreachable)}`);
      }
    }
  }

  function renderScreen() {
    // ⚠️ 先存成 const 再拿去 switch：narrowing 對 const 會存活進下面的 closure
    // （例如 onManageSchedules），不必再用型別斷言去繞過 TS 對 stack.current 這種
    // 屬性存取的保守判斷。
    const route = stack.current;
    switch (route.name) {
      case "login":
        return (
          <LoginScreen
            onRegister={() => push({ name: "register" })}
            onDone={() => reset({ name: "tabs" })}
          />
        );
      case "register":
        return (
          <RegisterScreen onLogin={() => stack.back()} onDone={() => reset({ name: "tabs" })} />
        );
      case "tabs":
        return (
          <div className="flex h-full min-h-0 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto">{renderTab()}</div>
            {addError ? (
              <div className="shrink-0 px-4 pb-1">
                <ErrorText message={addError} />
              </div>
            ) : null}
            <GuardianTabBar
              active={activeTab}
              onSelect={(tab) => {
                setActiveTab(tab);
                setAddError("");
              }}
              onAdd={() => void openAddReminder()}
              addBusy={addBusy}
              unread={unread}
              profileLabel={primaryElderLabel(primaryElder)}
            />
          </div>
        );
      case "elder":
        return (
          <ElderDetailScreen
            elderId={route.elderId}
            elderName={route.elderName}
            persona={route.persona}
            onManageSchedules={() =>
              push({
                name: "schedules",
                elderId: route.elderId,
                elderName: route.elderName,
              })
            }
            onOpenSummaries={() =>
              push({
                name: "summary",
                elderId: route.elderId,
                elderName: route.elderName,
              })
            }
            onSendCodeToElder={onSendCodeToElder}
          />
        );
      case "schedules":
        return (
          <SchedulesScreen
            elderId={route.elderId}
            elderName={route.elderName}
            onEditAppointment={(scheduleId) =>
              push({ name: "editAppointment", elderId: route.elderId, scheduleId })
            }
          />
        );
      case "summary":
        return <DailySummaryScreen elderId={route.elderId} />;
      case "editAppointment":
        return (
          <EditAppointmentScreen
            elderId={route.elderId}
            scheduleId={route.scheduleId}
            // 存檔或刪除成功後回上一頁——家屬要看到清單少一筆／時間改掉了。
            onDone={stack.back}
          />
        );
      default: {
        // 走到這裡代表新增了路由卻忘了接畫面。編譯期就會抓到（never 型別）。
        const unreachable: never = route;
        throw new Error(`未接線的家屬端畫面：${JSON.stringify(unreachable)}`);
      }
    }
  }

  // 返回鍵只在深層頁出現：分頁殼是最底層，沒有上一層可退；分頁之間用底部導覽列
  // 橫向切換，不該用「返回」。
  const canGoBack = stack.depth > 1;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {canGoBack ? <BackBar onBack={stack.back} /> : null}
      <div className="min-h-0 flex-1">{renderScreen()}</div>
    </div>
  );
}

function BackBar(props: { onBack: () => void }) {
  return (
    <button
      type="button"
      onClick={props.onBack}
      className="flex min-h-12 w-full shrink-0 items-center gap-1 border-b border-line bg-surface px-4 text-left text-sm font-semibold text-ink"
    >
      <span aria-hidden>‹</span>
      {strings.common.back}
    </button>
  );
}
