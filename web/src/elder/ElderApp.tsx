/**
 * 長輩端在手機外框內部的導覽。
 *
 * ⚠️ 與家屬端同樣不進瀏覽器網址列（見 nav/useScreenStack）。
 * ⚠️ 返回鍵比家屬端大：56px，而且字更大——長輩手指粗又常戴老花。
 * ⚠️ `visible` prop 轉交給 `BindScreen` 與 `TalkScreen`（見各自說明）：雙欄舞台
 * 窄螢幕頁籤模式下，這一欄被切到背景時要停止相機／麥克風與長連線，但不能卸載
 *（會丟掉打到一半的號碼）。`ElderApp` 自己不需要這個資訊。
 */

import { useCallback, useEffect, useState } from "react";

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

  /**
   * 被動登出（後端不認 token、或綁定失效）時要在配對畫面上講的那句話。
   *
   * ⚠️ **為什麼這句話住在這裡、不住在對講機或提醒畫面**：長輩被登出的那一刻，
   * 那兩個畫面就被配對畫面換掉了，寫在它們身上的說明一個字都不會被看到。他接下來
   * 唯一看得到的畫面是配對畫面，所以話要在**那裡**講。
   * ⚠️ 自己按登出**不**帶這句話：那是他自己做的事，不需要人解釋（`onLogout` 沒有
   * 呼叫 `loseSession`）。
   */
  const [signedOutNotice, setSignedOutNotice] = useState("");
  const loseSession = useCallback(
    (notice: string) => {
      setSignedOutNotice(notice);
      signOut();
    },
    [signOut],
  );
  // 重新登入成功就把上一次的說明收掉：不收的話他下次自己按登出，配對畫面會再說
  // 一次「家人幫您重新設定了」——那時根本沒有人幫他設定過任何東西。
  const enterTalk = useCallback(() => {
    setSignedOutNotice("");
    reset({ name: "talk" });
  }, [reset]);

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
            signedOutNotice={signedOutNotice}
            visible={visible}
            onDone={enterTalk}
            onLogin={() => stack.push({ name: "login" })}
          />
        );
      case "login":
        return <LoginScreen onDone={enterTalk} />;
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
            // 403＝家屬撤回了同意（token 還在，但閘門不讓這一輪過）。
            onBindingLost={() => loseSession(strings.talk.bindingLost)}
            // 401＝後端不認這支 token（家屬按了「重新產生長輩綁定碼」，或彩排後
            // 重建了資料庫）。⚠️ 這條路徑比 403 常見得多——後端撤 token 在拆綁定
            // **之前**，認證那一關就先擋下來了，403 幾乎到不了（見 useTalk 的說明）。
            onTokenRevoked={() => loseSession(strings.elderBind.signedOutByGuardian)}
          />
        );
      case "notifications":
        return (
          <NotificationsScreen
            onTokenRevoked={() => loseSession(strings.elderBind.signedOutByGuardian)}
          />
        );
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
