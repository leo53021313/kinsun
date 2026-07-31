/**
 * 家屬端在手機外框內部的導覽。
 *
 * ⚠️ 畫面切換是元件狀態、不進瀏覽器網址列（見 nav/useScreenStack 的說明）。
 * ⚠️ 未登入時一律強制回到登入畫面：session 被 401 清掉之後，若還停在長輩詳情頁，
 *    畫面會停在最後一次成功的資料上，讓人以為還連得上。
 */

import { useEffect } from "react";

import { useScreenStack } from "@/nav/useScreenStack";
import { GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";

import { ElderDetailScreen } from "./ElderDetailScreen";
import { HomeScreen } from "./HomeScreen";
import { LoginScreen } from "./LoginScreen";
import { NotificationsScreen } from "./NotificationsScreen";
import { RegisterScreen } from "./RegisterScreen";
import { SchedulesScreen } from "./SchedulesScreen";

export type GuardianRoute =
  | { name: "login" }
  | { name: "register" }
  | { name: "home" }
  | { name: "elder"; elderId: string; elderName: string }
  // elderName 跟著一起帶：家屬管兩位以上長輩時，行程管理頁若只有「行程管理」
  // 四個字，畫面上沒有任何字告訴他正在編誰的提醒。
  | { name: "schedules"; elderId: string; elderName: string }
  | { name: "notifications" };

export function GuardianApp(props: {
  /**
   * 把家屬產生的綁定碼直接送到長輩欄（spec W-15 內測捷徑）。轉交給
   * `HomeScreen`／`ElderDetailScreen`，接線見 `stage/StagePage.tsx`——
   * `GuardianApp` 自己不需要知道長輩欄的任何事，只單純往下傳。
   */
  onSendCodeToElder?: (code: string) => void;
  /** 通知未讀數（P4 Task 4，見 `stage/StagePage.tsx` 的 `guardianFeed.unread`）。轉交給 `HomeScreen`。 */
  unread?: number;
}) {
  const { onSendCodeToElder, unread } = props;
  const { session } = GuardianSession.useSession();
  const stack = useScreenStack<GuardianRoute>(session ? { name: "home" } : { name: "login" });
  const { reset } = stack;

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

  // stack.depth > 1 才顯示返回鍵：初始畫面（登入或首頁）沒有上一層可退。
  const canGoBack = stack.depth > 1;

  function renderScreen() {
    // ⚠️ 先存成 const 再拿去 switch：narrowing 對 const 會存活進下面的 closure
    // （例如 onManageSchedules），不必再用型別斷言去繞過 TS 對 stack.current 這種
    // 屬性存取的保守判斷。
    const route = stack.current;
    switch (route.name) {
      case "login":
        return (
          <LoginScreen
            onRegister={() => stack.push({ name: "register" })}
            onDone={() => reset({ name: "home" })}
          />
        );
      case "register":
        return <RegisterScreen onLogin={() => stack.back()} onDone={() => reset({ name: "home" })} />;
      case "home":
        return (
          <HomeScreen
            onOpenElder={(elderId, elderName) => stack.push({ name: "elder", elderId, elderName })}
            onOpenNotifications={() => stack.push({ name: "notifications" })}
            onSendCodeToElder={onSendCodeToElder}
            unread={unread}
          />
        );
      case "elder":
        return (
          <ElderDetailScreen
            elderId={route.elderId}
            elderName={route.elderName}
            onManageSchedules={() =>
              stack.push({
                name: "schedules",
                elderId: route.elderId,
                elderName: route.elderName,
              })
            }
            onSendCodeToElder={onSendCodeToElder}
          />
        );
      case "schedules":
        return <SchedulesScreen elderId={route.elderId} elderName={route.elderName} />;
      case "notifications":
        return <NotificationsScreen />;
      default: {
        // 走到這裡代表新增了路由卻忘了接畫面。編譯期就會抓到（never 型別）。
        const unreachable: never = route;
        throw new Error(`未接線的家屬端畫面：${JSON.stringify(unreachable)}`);
      }
    }
  }

  return (
    <>
      {canGoBack ? <BackBar onBack={stack.back} /> : null}
      {renderScreen()}
    </>
  );
}

function BackBar(props: { onBack: () => void }) {
  return (
    <button
      type="button"
      onClick={props.onBack}
      className="flex min-h-12 w-full items-center gap-1 border-b border-line bg-surface px-4 text-left text-sm font-semibold text-ink"
    >
      <span aria-hidden>‹</span>
      {strings.common.back}
    </button>
  );
}
