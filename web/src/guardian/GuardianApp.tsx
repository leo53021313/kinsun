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

import { HomeScreen } from "./HomeScreen";
import { LoginScreen } from "./LoginScreen";
import { RegisterScreen } from "./RegisterScreen";

export type GuardianRoute =
  | { name: "login" }
  | { name: "register" }
  | { name: "home" }
  | { name: "elder"; elderId: string; elderName: string }
  | { name: "schedules"; elderId: string }
  | { name: "notifications" };

export function GuardianApp() {
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

  switch (stack.current.name) {
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
        />
      );
    default:
      // elder／schedules／notifications 由 Task 5、6 接上。
      return <div className="p-5 text-ink-soft">{strings.common.notImplementedYet}</div>;
  }
}
