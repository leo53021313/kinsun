/**
 * 長輩看的提醒列表（X-01，2026-07-29）：用藥／回診提醒與主動關懷，最近先。
 *
 * ⚠️ 與家屬版（`guardian/NotificationsScreen.tsx`）刻意不共用元件：長輩版字級
 * 更大、行距更寬。共用會讓兩邊的排版約束互相拉扯，最後兩邊都不好看。
 *
 * ⚠️ **錯誤取代空狀態**（docs/dev/07 §7 的模組級不變量，家屬端首頁／行程／通知
 * 三處都因此修過）：載入失敗時**只**顯示錯誤，不落回「現在沒有要提醒您的事」
 * ——那句話向長輩承諾「沒事」，但這一刻我們根本沒查到任何東西，是一句假話，
 * 後果比家屬端更重：他會以為今天真的不用吃藥。沿用 `guardian/NotificationsScreen.tsx`
 * 已修過的寫法：`hasError` 是獨立的布林旗標，錯誤／載入中／空狀態／清單四段互斥，
 * 不把 `items` 一起清成 `[]`（清空的話「還沒有提醒」與「載入失敗」會同框出現）。
 */

import { formatTime } from "kinsun-shared/format";
import type { AppNotification } from "kinsun-shared/types";
import { useEffect, useState } from "react";

import { saveSeenAt } from "@/notify/seen";
import { ElderSession } from "@/session/contexts";
import { strings } from "@/strings";
import { ErrorText } from "@/ui/Feedback";

import { listElderNotifications } from "./api";

export function NotificationsScreen() {
  const { session } = ElderSession.useSession();
  const token = session?.token ?? "";
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (!token) {
      return;
    }
    let alive = true;
    listElderNotifications(token)
      .then((list) => {
        if (!alive) return;
        setItems(list);
        // 開啟即更新已讀水位：長輩不會去按「標示已讀」，看到就算看過。
        // 清單空的時候不動水位——歸零會讓舊提醒整批復活成未讀。
        if (list.length > 0) {
          try {
            // 用 Math.max 而非 list[0]：不能假設 API 回傳一定是新到舊，排序是
            // 後端的責任、不是這支元件的前提（guardian/NotificationsScreen.tsx
            // 同一個理由）。
            saveSeenAt(
              Math.max(...list.map((item) => item.created_at)),
              "elder",
            );
          } catch {
            // localStorage 寫入失敗（iOS Safari 無痕模式、儲存配額滿）不代表
            // 這輪讀取失敗——不可讓它被下面的 catch 誤判、把剛成功載入的清單
            // 整個蓋成「載入失敗」。
          }
        }
      })
      .catch(() => {
        if (!alive) return;
        setHasError(true);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  return (
    <div className="flex h-full flex-col gap-4 p-5">
      <h1 className="text-elder-min font-bold text-ink">{strings.elderNotifications.title}</h1>
      {hasError ? (
        <ErrorText message={strings.common.loadFailed} size="big" />
      ) : items === null ? (
        <p className="text-elder-min text-ink-soft">{strings.common.loading}</p>
      ) : items.length === 0 ? (
        <p className="text-elder-min leading-relaxed text-ink-soft">
          {strings.elderNotifications.empty}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => (
            <li
              key={`${item.created_at}-${item.content}`}
              className="flex flex-col gap-1 rounded-2xl border border-line bg-surface p-5"
            >
              <span className="text-base text-ink-soft">{formatTime(item.created_at)}</span>
              <span className="text-elder-min leading-relaxed text-ink">{item.content}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
