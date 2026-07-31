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
import { BindScreen, type ElderCodeDelivery } from "./BindScreen";
import { LoginScreen } from "./LoginScreen";
import { NotificationsScreen } from "./NotificationsScreen";
import { TalkScreen } from "./TalkScreen";

export type ElderRoute =
  | { name: "bind" }
  | { name: "login" }
  | { name: "talk" }
  | { name: "notifications" };

/**
 * 返回鍵要說的話，依「現在在哪個畫面」查——長輩端每一句都要告訴他下一步，
 * 而「返回」是這個原則下唯一一句抽象詞（`strings.elderNotifications.back`
 * 「回去講話」在 Task 9 就寫好了，只是沒有人接上）。
 *
 * ⚠️ **不把標籤塞進 `ElderRoute` 型別**：那會讓 `push`／`reset` 的每一個呼叫端
 * 都得帶一串字，而那串字跟「要去哪一頁」是兩回事。查不到就退回
 * `strings.common.back`——新增路由時漏了這裡，最差也只是回到現況。
 */
const BACK_LABELS: Partial<Record<ElderRoute["name"], string>> = {
  notifications: strings.elderNotifications.back,
  login: strings.elderLogin.back,
};

/**
 * ⚠️ `prefilledCode` 是「家屬欄把剛產生的碼直接送到長輩欄」那條內測捷徑的**接收端**
 *（spec W-15，P4 Task 3 接上發送端：`stage/StagePage.tsx` 持有這個狀態，往下
 * 傳給這裡，並把 `guardian/GuardianApp.tsx` 的 `onSendCodeToElder` 一路轉交給
 * `HomeScreen`／`ElderDetailScreen`，最終掛在 `InviteCard` 的 `onSendToElder`）。
 *
 * ⚠️ **這裡本身不需要改**（往下轉交給 `BindScreen` 即可）。`prefilledCode` 的
 * 型別是 `ElderCodeDelivery`（`{ code, seq }`，見 `BindScreen.tsx` 的型別說明）
 * ——**送出是一次事件，不是單純的值**：全分支審查發現若只當成 `string`，會
 * 讓「長輩配對成功又被登出、重新掛回這個畫面」誤讀到舊碼、以及「同一組碼再送
 * 一次」被誤判成沒有變化而略過同步。`BindScreen` 以 render 期間比對 `seq`
 * 是否變動來決定要不要同步，不在掛載時把 props 目前的值當成初始值（見該檔
 * 說明）。
 */
export function ElderApp(props: { prefilledCode?: ElderCodeDelivery; visible?: boolean }) {
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
            onLogout={() => {
              // 撤伺服器端的 token（✅ 庚-42 長輩自助登出），但**不等它**：撤不掉
              // 也不擋本機登出——網路不通時長輩仍然要能把手機交還給家人。
              //
              // ⚠️ 原本寫成 `await …catch(() => undefined)`：`.catch()` 擋得住
              // reject，**擋不住 hang**。Cloudflare 隧道「接受連線後不回應」正是這個
              // 形狀，而 `fetch` 沒有逾時——那條路上按下「確定登出」之後畫面就停在
              // 對講機，不會有任何反應。註解寫的「撤不掉也不擋本機登出」與程式行為
              // 因此在 hang 這條路上對不起來。不等它，兩者就一致了：請求照樣送出去，
              // 成不成功都不影響長輩把手機交還給家人。
              void logoutSession(session?.token ?? "").catch(() => undefined);
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
          {BACK_LABELS[stack.current.name] ?? strings.common.back}
        </button>
      ) : null}
      <div className="min-h-0 flex-1">{body}</div>
    </div>
  );
}
