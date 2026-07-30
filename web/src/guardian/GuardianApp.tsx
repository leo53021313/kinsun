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
    default:
      // home 與其後的畫面由 Task 4～6 接上。
      return <HomePlaceholder />;
  }
}

/** Task 4 換成真的 HomeScreen。 */
function HomePlaceholder() {
  return <h1 className="p-5 text-lg font-bold text-ink">{strings.guardianHome.title}</h1>;
}
