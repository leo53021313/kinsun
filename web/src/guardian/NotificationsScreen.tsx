import { formatTime } from "kinsun-shared/format";
import type { AppNotification } from "kinsun-shared/types";
import { useEffect, useMemo, useState } from "react";

import { saveSeenAt } from "@/notify/seen";
import { toBannerSeverity } from "@/notify/severity";
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
  // ⚠️ 布林旗標、不是字串訊息：錯誤文字一律用固定的 strings.common.loadFailed，
  // 不把 items 一起清成 []——那樣會讓「查詢失敗」與「查了、真的沒有通知」這兩件
  // 事在畫面上長得一樣，而後者的文案「金孫有事會第一時間放在這裡」在前者當下
  // 是一句假話（見 ElderDetailScreen.tsx 的 reportError／summariesError／
  // groupsError 三個旗標，此處沿用同一種寫法）。
  const [hasError, setHasError] = useState(false);

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
          try {
            // 用 Math.max 而非 list[0]：這裡不能假設 API 回傳一定是新到舊，
            // 排序是後端的責任、不是這支元件的前提；就算哪天排序變了，水位
            // 仍要落在真正最新的那一則，不能悄悄存成最舊的一則。
            saveSeenAt(
              Math.max(...list.map((item) => item.created_at)),
              "guardian",
            );
          } catch {
            // localStorage 寫入失敗（例如 iOS Safari 無痕模式、儲存配額滿）
            // 不代表這輪讀取失敗——不可讓它被下面的 catch 誤判、把剛成功
            // 載入的清單蓋掉。
          }
        }
      })
      .catch((exc) => {
        if (signOutOn401(exc)) return;
        if (alive) setHasError(true);
      });
    return () => {
      alive = false;
    };
  }, [token, signOutOn401]);

  return (
    <div className="flex flex-col gap-3 p-4">
      <h1 className="text-lg font-bold text-ink">{strings.notifications.title}</h1>
      {hasError ? (
        <ErrorText message={strings.common.loadFailed} />
      ) : items === null ? (
        <EmptyHint text={strings.common.loading} />
      ) : items.length === 0 ? (
        <EmptyHint text={strings.notifications.empty} />
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => {
            // ⚠️ 一律過 `toBannerSeverity`（不直接讀 `item.severity`）：欄位可能
            // 缺席或是這一版前端不認得的值，收斂規則只有 `notify/severity.ts`
            // 一個地方——兩支 NotificationsScreen 與橫幅共用同一份判斷。
            const isAlert = toBannerSeverity(item.severity) === "alert";
            return (
              <li
                key={`${item.created_at}-${item.content}`}
                data-severity={isAlert ? "alert" : "notice"}
                className={`flex flex-col gap-1 rounded-2xl p-4 ${
                  isAlert ? "border-2 border-danger bg-surface" : "border border-line bg-surface"
                }`}
              >
                {/* ⚠️ **文字標籤不可省，不能只靠紅框**（裁決 4，2026-08-01）：
                    WCAG 1.4.1「Use of Color」——顏色不可是傳達資訊的唯一手段。
                    讀螢幕的家屬收不到紅框，色覺辨認障礙者也可能收不到；這行字
                    是他們唯一分得出「這則是危急」的線索。文案沿用橫幅那一句，
                    同一個概念在系統裡只有一個名字。 */}
                {isAlert ? (
                  <span className="text-xs font-bold text-danger">{strings.notify.alertTitle}</span>
                ) : null}
                <span className="text-xs text-ink-soft">{formatTime(item.created_at)}</span>
                <span className="text-sm leading-6 text-ink">{item.content}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
