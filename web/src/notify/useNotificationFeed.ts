/**
 * 通知輪詢：把後端主動產生的東西（危急警報、排程提醒）變成畫面上的橫幅。
 *
 * ⚠️ 為什麼是輪詢而不是 WebSocket：長輩端的 WS 是對講機專用的，家屬端根本沒有
 * 連線。替家屬端另開一條下行通道是後端的新工作，而這個規模的併發（展示現場
 * 十幾個人）用兩秒輪詢完全吃得住。
 *
 * ⚠️ **第一次載入不補播歷史**：那是展示現場最尷尬的失敗——一進站就滑進十幾張
 * 橫幅、蓋滿整個手機。第一次的用途是「記下目前的水位」。
 *
 * ⚠️ **本檔的「水位」跟 `notify/seen.ts` 的已讀水位是兩件不同的東西，刻意不共用
 * 寫入權**（修正 brief 缺陷；見下方「brief 缺陷」段）：`loadSeenAt`／`saveSeenAt`
 * 的寫入權**只**屬於 `elder/NotificationsScreen.tsx`／`guardian/NotificationsScreen.tsx`
 * ——那兩支畫面「開啟即更新已讀水位」，代表使用者真的把清單捲過一遍，未讀徽章
 * 才因此有意義。這裡只**讀**已讀水位（算 `unread` 用），另外自己養一支純記憶體
 * 的游標（`shownUpTo`），只管「這則有沒有已經變成橫幅播過」。
 *
 * brief 缺陷（已修，阻斷性——`unread` 原本恆為 0）：brief 原始版本在同一個
 * `seenAt` 上又讀又寫——`poll()` 每輪都把 `seenAt.current` 推到「這一批資料裡
 * 最新一則」再存回 `localStorage`，緊接著才用 `loadSeenAt()` 讀回剛剛存的同一個
 * 值去算 `unread`。可以證明這樣算出來的 `unread` **永遠是 0**：`loadSeenAt()`
 * 讀到的水位已經 ≥ 這一批任何一則的 `created_at`，`created_at > 水位` 這個條件
 * 因此無論如何都不成立。徽章的意義就此消失——使用者連提醒列表都還沒點開，
 * 紅點卻已經自己歸零。已改為徽章只讀 `notify/seen.ts` 的已讀水位（隨輪詢即時
 * 反映使用者「真的看過」與否），輪詢本身完全不寫這支水位。
 */

import type { AppNotification } from "kinsun-shared/types";
import { useCallback, useEffect, useRef, useState } from "react";

import { listElderNotifications } from "@/elder/api";
import { listNotifications } from "@/guardian/api";
import { strings } from "@/strings";

import type { BannerItem } from "./NotificationBanner";
import { loadSeenAt, unreadCount, type Audience } from "./seen";

const DEFAULT_INTERVAL_MS = 2000;
/** 橫幅顯示時間：3.5 秒足夠看完一句話，又不會擋住底下的操作太久。 */
const DISMISS_MS = 3500;

/**
 * 佇列上限（審查發現：brief 原始版本 `queue.current.push(...)` 沒有上限）。
 *
 * 這支 hook 只要掛著就會一直輪詢，展示現場常見「開著但很久沒人管」，沒有上限
 * 的話還沒播出去的橫幅會一路累積，記憶體與「使用者要等多久才追得上」都是無界
 * 的。20 是沒有精確依據的判斷：一天下來合理量級的用藥／回診提醒＋主動關懷不會
 * 逼近這個數字，真的塞爆多半代表使用者離開很久、或後端在補一大批積壓資料，
 * 這時「一則不漏地播完歷史」的價值已經不高，寧可捨舊留新（見下方 eviction）。
 * 展示現場若發現不合用可再調整這個數字。
 */
export const QUEUE_MAX = 20;

/** 純函式：挑出比水位新的那些。水位為 0（從未看過）時一律不算新的。 */
export function pickNewItems(items: AppNotification[], sinceAt: number): AppNotification[] {
  if (sinceAt === 0) {
    return [];
  }
  return items
    .filter((item) => item.created_at > sinceAt)
    .sort((a, b) => b.created_at - a.created_at);
}

export function useNotificationFeed(options: {
  audience: Audience;
  token: string;
  intervalMs?: number;
  /** 值一變就立刻重拉一次（供未來跨欄連動使用，如「家屬剛設了新排程」）。 */
  reloadSignal?: number;
}) {
  const { audience, token, intervalMs = DEFAULT_INTERVAL_MS, reloadSignal = 0 } = options;
  const [banner, setBanner] = useState<BannerItem | null>(null);
  const [unread, setUnread] = useState(0);
  // 佇列而非直接覆寫：一次輪詢可能拿到兩則新的（排程提醒剛好與危急警報同時），
  // 直接覆寫會讓第一則在畫面上一閃而過。
  const queue = useRef<BannerItem[]>([]);
  /**
   * 純記憶體游標：「這則有沒有已經變成橫幅播過」，跟 `notify/seen.ts` 的已讀
   * 水位是兩回事（見檔頭說明）。掛載或換人時從已讀水位起跳，只是為了讓「第一次
   * 不補播歷史」這條規則對新的這個人一樣成立；之後就不再回頭寫 `localStorage`。
   * 換人時的重設見下方「render 期間比對」那段；這裡的初始值只服務掛載那一刻。
   */
  const shownUpTo = useRef(loadSeenAt(audience));
  /**
   * 卸載後才回來的輪詢結果整批丟棄用（審查發現：brief 原始版本的 `alive` 只擋得住
   * 「排下一次」，擋不住「已經在飛的這一次」——`run()` 在卸載前那一刻被觸發、卻在
   * 卸載後才 resolve 時，`poll()` 內文照樣會繼續往下改 state／`queue.current`）。
   */
  const mountedRef = useRef(true);
  /**
   * 「現在是誰」：換人（`audience`／`token` 改變）時更新，供 `poll()` resolve
   * 之後自我核對。**只有 `mountedRef` 擋不住這條路徑**：換人不會讓元件卸載，
   * 只會讓 `poll` 換一顆新的閉包——舊那顆還在飛的呼叫不受影響，resolve 之後
   * 一樣會照跑，若不比對就會拿著上一位使用者的資料去更新新使用者的橫幅／
   * 已讀游標／佇列（用手動控制的 promise 實測證實過這條路徑真的會發生，見
   * 測試「換人時，前一位使用者還在飛的輪詢結果晚到」）。
   */
  const sessionRef = useRef({ audience, token });

  const shift = useCallback(() => {
    setBanner(queue.current.shift() ?? null);
  }, []);

  const poll = useCallback(async () => {
    if (!token) return;
    const items =
      audience === "guardian" ? await listNotifications(token) : await listElderNotifications(token);
    if (!mountedRef.current) return;
    // 這批資料還在飛的時候使用者已經換過了：不是「現在這個人」的，整批丟棄。
    if (sessionRef.current.audience !== audience || sessionRef.current.token !== token) return;
    const fresh = pickNewItems(items, shownUpTo.current);
    if (items.length > 0) {
      shownUpTo.current = Math.max(shownUpTo.current, ...items.map((item) => item.created_at));
    }
    // 徽章只讀已讀水位（見檔頭「brief 缺陷」說明）：使用者沒開過提醒列表之前，
    // 就算橫幅已經播過也還算未讀——「已讀」這兩個字在這個產品裡只有一個定義
    // 來源，就是那兩支 NotificationsScreen。
    setUnread(unreadCount(items, loadSeenAt(audience)));
    if (fresh.length > 0) {
      // 最舊的先播——事情發生的順序才是使用者理解得了的順序。
      const incoming = fresh
        .slice()
        .reverse()
        .map((item) => ({
          id: `${item.created_at}-${item.content}`,
          title: strings.gate.brand,
          content: item.content,
          at: item.created_at,
        }));
      // 滿了丟最舊的：slice(-QUEUE_MAX) 保留陣列尾端（較新的那些）。積壓愈久
      // 愈舊的通知，時效性愈低，寧可讓使用者看到「最近發生的事」。
      queue.current = [...queue.current, ...incoming].slice(-QUEUE_MAX);
      setBanner((current) => current ?? queue.current.shift() ?? null);
    }
  }, [audience, token]);

  /**
   * 換人（audience 或 token 換掉）：橫幅立刻清空，不讓上一位使用者的殘留畫面
   * 留到新的這個人身上。
   *
   * ⚠️ 這段刻意寫成「render 期間比對＋調整」（React 官方文件「Adjusting some
   * state when a prop changes」的既定寫法），不是 `useEffect`：改在 `useEffect`
   * 裡直接呼叫 `setBanner` 會先掛著上一位使用者的殘留橫幅多畫一次畫面、下一輪
   * render 才收掉（`react-hooks/set-state-in-effect` 擋下的正是這種會多一輪
   * cascading render 的寫法）。`lastSession` 只用來偵測「這一輪的 audience／token
   * 跟上一輪比對是否換了」，一旦換了就在同一次 render 內把 `banner` 歸零，
   * 使用者不會看到殘留橫幅先閃一下才消失。
   *
   * ⚠️ 佇列／游標（`queue`／`shownUpTo`／`sessionRef`）不能放在這裡一起歸零：
   * 這幾個是 ref，`react-hooks/refs` 不准在 render 期間讀寫 ref（會讓 React
   * 判斷「這個元件要不要更新」的邏輯跟著亂掉）。改放到下面那顆只碰 ref、
   * 完全不呼叫任何 state setter 的獨立 `useEffect`。
   */
  const [lastSession, setLastSession] = useState({ audience, token });
  if (lastSession.audience !== audience || lastSession.token !== token) {
    setLastSession({ audience, token });
    setBanner(null);
  }

  // 上面那段的 ref 版本：佇列／游標／「現在是誰」都在這裡歸零，讓「第一次不
  // 補播歷史」對新的這個人同樣成立。effect 本身完全不呼叫任何 state setter。
  useEffect(() => {
    sessionRef.current = { audience, token };
    queue.current = [];
    shownUpTo.current = loadSeenAt(audience);
  }, [audience, token]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    const run = () => {
      // 輪詢失敗完全靜默：通知是加分項，網路抖一下不該在畫面上留紅字。
      void poll().catch(() => undefined);
    };
    const tick = () => {
      // 瀏覽器分頁被切到背景時不打這一輪：展示現場常見「開著但沒在看」，
      // 沒必要在背景繼續打後端、繼續把佇列塞滿。切回前景時下面的監聽器
      // 會立刻補一次，不必等到下一次輪詢間隔。
      if (alive && !document.hidden) run();
    };
    run();
    const timer = setInterval(tick, intervalMs);
    const onVisible = () => {
      if (alive && !document.hidden) run();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [poll, token, intervalMs, reloadSignal]);

  // 橫幅自動消失。3.5 秒足夠看完一句話，又不會擋住底下的操作太久。
  //
  // ⚠️ 這條 effect 綁的是 `banner`（值）：`banner` 換成下一則時 React 會先跑上一輪
  // 的 cleanup（`clearTimeout` 掉上一則自己的計時器）才跑這一輪，兩則橫幅的倒數
  // 因此各自獨立、不會互相打斷或提前關掉（已用測試逐格推進計時器釘住這件事）。
  useEffect(() => {
    if (banner === null) return;
    const timer = setTimeout(shift, DISMISS_MS);
    return () => clearTimeout(timer);
  }, [banner, shift]);

  return { banner, unread, dismiss: shift, reload: () => void poll().catch(() => undefined) };
}
