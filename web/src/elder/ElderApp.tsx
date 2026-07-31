/**
 * 長輩端在手機外框內部的導覽。
 *
 * ⚠️ 與家屬端同樣不進瀏覽器網址列（見 nav/useScreenStack）。
 * ⚠️ 返回鍵比家屬端大：56px，而且字更大——長輩手指粗又常戴老花。
 * ⚠️ `visible` prop 轉交給 `BindScreen` 與 `TalkScreen`（見各自說明）：雙欄舞台
 * 窄螢幕頁籤模式下，這一欄被切到背景時要停止相機／麥克風與長連線，但不能卸載
 *（會丟掉打到一半的號碼）。`ElderApp` 自己不需要這個資訊。
 */

import { useEffect } from "react";

import { useScreenStack } from "@/nav/useScreenStack";
import { ElderSession } from "@/session/contexts";
import { strings } from "@/strings";

import { logoutSession } from "./api";
import { BindScreen } from "./BindScreen";
import { LoginScreen } from "./LoginScreen";
import { NotificationsScreen } from "./NotificationsScreen";
import { TalkScreen } from "./TalkScreen";

export type ElderRoute =
  | { name: "bind" }
  | { name: "login" }
  | { name: "talk" }
  | { name: "notifications" };

export function ElderApp(props: { prefilledCode?: string; visible?: boolean }) {
  const { visible = true } = props;
  const { session, signOut } = ElderSession.useSession();
  const stack = useScreenStack<ElderRoute>(session ? { name: "talk" } : { name: "bind" });
  const { reset } = stack;

  // 登入狀態消失（登出或綁定失效）就回到配對畫面。留在原畫面的話，上面會停著
  // 最後一次成功的內容，看起來像還連得上。
  const loggedIn = session !== null;
  useEffect(() => {
    if (!loggedIn) {
      reset({ name: "bind" });
    }
  }, [loggedIn, reset]);

  const body = (() => {
    switch (stack.current.name) {
      case "bind":
        return (
          <BindScreen
            prefilledCode={props.prefilledCode}
            visible={visible}
            onDone={() => reset({ name: "talk" })}
            onLogin={() => stack.push({ name: "login" })}
          />
        );
      case "login":
        return <LoginScreen onDone={() => reset({ name: "talk" })} />;
      case "talk":
        return (
          <TalkScreen
            token={session?.token ?? ""}
            // P4 接上通知輪詢時換成真的數字（Task 9 補提醒列表本身）。
            unread={0}
            visible={visible}
            onOpenNotifications={() => stack.push({ name: "notifications" })}
            onLogout={async () => {
              // 先撤伺服器端的 token（✅ 庚-42 長輩自助登出）；撤不掉也不擋本機
              // 登出——網路不通時長輩仍然要能把手機交還給家人。
              await logoutSession(session?.token ?? "").catch(() => undefined);
              signOut();
            }}
            // 403＝這台手機的綁定失效了。清掉 session，上面的守衛會把他導回配對。
            onBindingLost={signOut}
          />
        );
      case "notifications":
        return <NotificationsScreen />;
      default: {
        // 走到這裡代表新增了路由卻忘了接畫面。編譯期就會抓到（never 型別，
        // 與家屬端 GuardianApp 同款窮盡檢查）。
        const unreachable: never = stack.current;
        throw new Error(`未接線的長輩端畫面：${JSON.stringify(unreachable)}`);
      }
    }
  })();

  return (
    <div className="flex h-full flex-col">
      {stack.depth > 1 ? (
        <button
          type="button"
          onClick={stack.back}
          // 56px：長輩端的可觸控目標比家屬端再大一級。
          className="flex min-h-14 w-full items-center gap-1 border-b border-line bg-surface px-5 text-left text-elder-min text-ink"
        >
          <span aria-hidden>‹</span>
          {strings.common.back}
        </button>
      ) : null}
      <div className="min-h-0 flex-1">{body}</div>
    </div>
  );
}
