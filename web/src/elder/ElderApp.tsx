/**
 * 長輩端在手機外框內部的導覽。
 *
 * ⚠️ 與家屬端同樣不進瀏覽器網址列（見 nav/useScreenStack）。
 * ⚠️ 返回鍵比家屬端大：56px，而且字更大——長輩手指粗又常戴老花。
 */

import { useEffect } from "react";

import { useScreenStack } from "@/nav/useScreenStack";
import { ElderSession } from "@/session/contexts";
import { strings } from "@/strings";

import { BindScreen } from "./BindScreen";
import { LoginScreen } from "./LoginScreen";

export type ElderRoute =
  | { name: "bind" }
  | { name: "login" }
  | { name: "talk" }
  | { name: "notifications" };

export function ElderApp(props: { prefilledCode?: string }) {
  const { session } = ElderSession.useSession();
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
            onDone={() => reset({ name: "talk" })}
            onLogin={() => stack.push({ name: "login" })}
          />
        );
      case "login":
        return <LoginScreen onDone={() => reset({ name: "talk" })} />;
      default:
        // talk 與 notifications 由 Task 8、9 接上。文案仍走 strings.ts——
        // 即使是暫時性的佔位畫面，元件裡也不可出現裸中文字串。
        return <div className="p-5 text-elder-min text-ink-soft">{strings.common.comingSoon}</div>;
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
