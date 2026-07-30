import { formatTime } from "kinsun-shared/format";
import type { AppNotification } from "kinsun-shared/types";
import { useEffect, useMemo, useState } from "react";

import { saveSeenAt } from "@/notify/seen";
import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { EmptyHint, ErrorText } from "@/ui/Feedback";

import { listNotifications } from "./api";

export function NotificationsScreen() {
  const { session, signOut } = GuardianSession.useSession();
  const token = session?.token ?? "";
  // ⚠️ 用 useMemo 而非 useCallback：makeSignOutOnAuthError 是**工廠**，回傳的是函式
  // 值，而 useCallback 收的應該是行內函式表達式——react-hooks 的規則會擋下來。
  // signOut 在 session 工廠裡是 useCallback([]) 的穩定參考，所以這個值也穩定，
  // 不會讓下面的 effect 反覆重打 API。
  const signOutOn401 = useMemo(() => makeSignOutOnAuthError(signOut), [signOut]);
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    let alive = true;
    listNotifications(token)
      .then((list) => {
        if (!alive) return;
        setItems(list);
        // 開啟即更新已讀水位：家屬不會去按「標示已讀」，看到就算看過。
        // 清單空的時候不要動水位——歸零會讓舊通知整批復活成未讀。
        if (list.length > 0) {
          saveSeenAt(list[0].created_at, "guardian");
        }
      })
      .catch((exc) => {
        if (signOutOn401(exc)) return;
        if (alive) {
          setItems([]);
          setError(strings.common.loadFailedShort);
        }
      });
    return () => {
      alive = false;
    };
  }, [token, signOutOn401]);

  return (
    <div className="flex flex-col gap-3 p-4">
      <h1 className="text-lg font-bold text-ink">{strings.notifications.title}</h1>
      <ErrorText message={error} />
      {items === null ? (
        <EmptyHint text={strings.common.loading} />
      ) : items.length === 0 ? (
        <EmptyHint text={strings.notifications.empty} />
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li
              key={`${item.created_at}-${item.content}`}
              className="flex flex-col gap-1 rounded-2xl border border-line bg-surface p-4"
            >
              <span className="text-xs text-ink-soft">{formatTime(item.created_at)}</span>
              <span className="text-sm leading-6 text-ink">{item.content}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
