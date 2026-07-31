/**
 * 通知輪詢：把後端主動產生的東西（危急警報、排程提醒）變成畫面上的橫幅。
 *
 * ⚠️ 為什麼是輪詢而不是 WebSocket：長輩端的 WS 是對講機專用的，家屬端根本沒有
 * 連線。替家屬端另開一條下行通道是後端的新工作，而這個規模的併發（展示現場
 * 十幾個人）用兩秒輪詢完全吃得住。⚠️ **量化備查（審查要求）**：兩欄（長輩＋
 * 家屬）同時輪詢＝每個瀏覽器 1 req/s，後端每次請求約跑三段查詢（token 驗證＋
 * `app_external_ids_of_*`／`app_external_id_of_elder`＋`list_for_external_ids`）；
 * 展示現場十幾人約 **15 req/s、40+ 次 DB 查詢/秒**。吃得住，但值得記下來供
 * 日後評估是否要調大 `intervalMs` 或改真推播。
 *
 * ⚠️ **第一次載入不補播歷史，且這件事跟使用者有沒有開過提醒列表無關**（審查
 * 發現第二個阻斷性缺陷，見下方「brief 缺陷 2」）：那是展示現場最尷尬的失敗——
 * 一進站就滑進十幾張橫幅、蓋滿整個手機。「第一次」的判斷**不是**看
 * `notify/seen.ts` 的已讀水位是不是 0，是看**這支 hook 自己有沒有為目前這組
 * audience／token 成功跑過至少一輪輪詢**：只要還沒跑過第一輪，不管既有已讀
 * 水位多舊、水位之後累積了多少通知，一律不當成新的補播出來。
 *
 * ⚠️ **本檔的「水位」跟 `notify/seen.ts` 的已讀水位是兩件不同的東西，刻意不共用
 * 寫入權**：`loadSeenAt`／`saveSeenAt` 的寫入權**只**屬於
 * `elder/NotificationsScreen.tsx`／`guardian/NotificationsScreen.tsx`——那兩支
 * 畫面「開啟即更新已讀水位」，代表使用者真的把清單捲過一遍，未讀徽章才因此
 * 有意義。這裡只**讀**已讀水位（算 `unread` 用），另外自己養一支純記憶體的
 * 游標（`shownUpTo`），只管「這則有沒有已經變成橫幅播過」——這支游標**不從
 * 已讀水位起跳**（見下方 brief 缺陷 2），一律從 0（從未跑過）開始。
 *
 * brief 缺陷 1（已修，阻斷性——`unread` 原本恆為 0）：brief 原始版本在同一個
 * `seenAt` 上又讀又寫——`poll()` 每輪都把 `seenAt.current` 推到「這一批資料裡
 * 最新一則」再存回 `localStorage`，緊接著才用 `loadSeenAt()` 讀回剛剛存的同一個
 * 值去算 `unread`。可以證明這樣算出來的 `unread` **永遠是 0**：`loadSeenAt()`
 * 讀到的水位已經 ≥ 這一批任何一則的 `created_at`，`created_at > 水位` 這個條件
 * 因此無論如何都不成立。徽章的意義就此消失——使用者連提醒列表都還沒點開，
 * 紅點卻已經自己歸零。已改為徽章只讀 `notify/seen.ts` 的已讀水位（隨輪詢即時
 * 反映使用者「真的看過」與否），輪詢本身完全不寫這支水位。
 *
 * brief 缺陷 2（已修，阻斷性——**審查發現**，第一版修正的「第一次不補播歷史」
 * 沒有真的成立）：第一版修正把 `shownUpTo` 的初始值與換人時的重設都設成
 * `loadSeenAt(audience)`——用意是「至少從已讀水位開始算」，但兩支
 * `NotificationsScreen` 開啟時會把已讀水位存成「當時最新一則」，所以只要使用者
 * 曾經開過一次提醒列表、之後有任何新通知累積，水位就不是 0，這支 hook 掛載時
 * 會把「上次開列表之後的全部通知」整批當成新的一次播完（審查實測：已讀水位
 * 存在時掛載即播出 7 則，20 則上限下最壞可以連播 70 秒）——這正是本檔與 brief
 * 都稱為「展示現場最尷尬的失敗」的那件事，只是換了個時機發生而已。已改為
 * `shownUpTo` 一律從 `0` 起跳（掛載與換人皆同，不再讀已讀水位）；第一輪輪詢
 * 只用來記下目前的水位，不管當下已經累積了多少通知都不播。
 *
 * ⚠️ **接線狀態（P4 Task 4 已接，見 `stage/StagePage.tsx`）**：
 * 1) `visible?: boolean`（本輪已加進簽章並接上）：窄螢幕頁籤模式下，非活動欄
 *    （同 `elder/useTalk.ts` 的 `visible` 語意）現在會在 `!visible` 時整段跳過
 *    輪詢（含不註冊分頁可見性監聽器），由 `StagePage.tsx` 的 `elderVisible`／
 *    `guardianVisible` 傳入——與相機／麥克風走同一條線，理由同該檔說明：非
 *    活動欄只是被 CSS `hidden` 蓋住，元件仍掛著，計時器與 `display:none` 無關。
 * 2) `onTokenRevoked?: () => void`（本輪已接上）：`stage/StagePage.tsx` 傳入
 *    對應 session 的 `signOut`。⚠️ **已知落差**：這裡只會清掉 session、把
 *    `ElderApp`／`GuardianApp` 導回配對／登入畫面，**不會**帶出
 *    `elder/ElderApp.tsx` 那句「家人幫您重新設定了…」的說明——那句話掛在
 *    `ElderApp` 自己的 `loseSession`，本 hook 活在舞台層、構造上碰不到它。
 *    是否要把這句說明也接上，留給下一輪裁決（多一條跨元件的訊息通道，是否
 *    值得為這個邊角情境增加複雜度）。
 *
 * ⚠️ **已知限制（非本工項新缺陷，W-13 同款）**：窄螢幕頁籤模式下，橫幅在被
 * CSS 蓋住的那一欄一樣會照常播出、3.5 秒後照樣自動消失——使用者切過去看的
 * 時候已經錯過了。資料本身不會遺失（仍在提醒列表與未讀數裡），只有「即時跳
 * 出來」這個效果會被錯過；切走那一刻**已經**顯示著的那一則仍會照原訂時間
 * 自動消失，不受影響。
 *
 * ⚠️ **`visible` 切回 `true` 時會重建基準，不會補播隱藏期間累積的通知**
 *（審查發現的 Important 2，2026-08-01，修正前這裡曾誤宣稱「非活動欄不再
 * 繼續累積新的橫幅」就等於「沒有副作用」——那句話本身沒錯，但漏了它的
 * **結果**：`shownUpTo` 若不隨可見性重設，切回來的第一輪會把隱藏期間累積的
 * 每一則都當成新的一次補播出來，一則 3.5 秒、`QUEUE_MAX` 上限下最壞連播
 * 70 秒，這正是本檔反覆稱為「展示現場最尷尬的失敗」的那件事，只是換了個
 * 時機發生。已在下方輪詢 effect 補上：`visible` 由 `false` 轉 `true` 時把
 * `shownUpTo.current` 重設為 `0`，讓那一輪跟掛載時一樣只重建基準。
 *
 * ⚠️ **已知限制（後端）**：`unread` 徽章依賴的 `list_for_external_ids` 後端
 * 有 `LIMIT 50`（`src/kinsun/notifications/store.py`），未開放成可調整的查詢
 * 參數。展示規模碰不到這個上限，記錄備查。
 */

import type { AppNotification } from "kinsun-shared/types";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api";
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
  /**
   * 後端不認這支 token（401，例如家屬按了「重新產生長輩綁定碼」）。見檔頭
   * 「接線狀態 2」。
   */
  onTokenRevoked?: () => void;
  /**
   * 這一欄目前是否真的看得見（雙欄舞台在窄螢幕是頁籤擇一顯示，見
   * `stage/StagePage.tsx`）。見檔頭「接線狀態 1」。預設 `true`（與
   * `elder/useTalk.ts` 的預設一致，維持非舞台情境下呼叫端不必知道這個概念）。
   */
  visible?: boolean;
}) {
  const {
    audience,
    token,
    intervalMs = DEFAULT_INTERVAL_MS,
    reloadSignal = 0,
    onTokenRevoked,
    visible = true,
  } = options;
  const [banner, setBanner] = useState<BannerItem | null>(null);
  const [unread, setUnread] = useState(0);
  // 佇列而非直接覆寫：一次輪詢可能拿到兩則新的（排程提醒剛好與危急警報同時），
  // 直接覆寫會讓第一則在畫面上一閃而過。
  const queue = useRef<BannerItem[]>([]);
  /**
   * 純記憶體游標：「這則有沒有已經變成橫幅播過」，跟 `notify/seen.ts` 的已讀
   * 水位是兩回事（見檔頭說明）。**一律從 0 起跳**（掛載與換人皆同，見下方
   * 「render 期間比對」那段），不讀已讀水位——讀已讀水位曾經是這裡的寫法，
   * 審查抓到那樣「第一次不補播歷史」並不會真的成立（見檔頭 brief 缺陷 2）。
   */
  const shownUpTo = useRef(0);
  /**
   * 上一輪的 `visible`，供下方輪詢 effect 判斷「是不是剛從不可見轉為可見」
   * （審查發現的 Important 2，2026-08-01，見該處說明）。初始值等於掛載當下的
   * `visible`——掛載本身不算「轉換」，`shownUpTo` 已經由下方換人／掛載的
   * `useEffect` 歸零過一次，不需要在這裡重複判斷。
   */
  const wasVisibleRef = useRef(visible);
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
   *
   * ⚠️ **已知殘留窗口（審查標明，時序論證非實測，jsdom 無法重現）**：這裡的
   * 更新（見下方 effect）走 passive effect，發生在 commit 之後；而
   * `poll()` 的 continuation 是 microtask、passive effect 的 flush 走的是
   * macrotask。理論上存在一個約一個 frame 寬的窗口——`poll()` 剛好在
   * `sessionRef` 被更新**之前**的那個瞬間 resolve——這條檢查仍會誤判為
   * 「還是同一個人」。尚未找到能在 jsdom 重現的辦法，記錄在此讓下一個人
   * 知道這條路徑還沒完全關死，不是宣稱它已經無懈可擊。
   */
  const sessionRef = useRef({ audience, token });
  /**
   * `banner` 狀態的鏡射，供 `poll()` 判斷「現在有沒有橫幅正在顯示」用（審查
   * 發現的 Important 2）：brief 與第一版修正都直接在 `setBanner` 的 updater
   * 函式裡呼叫 `queue.current.shift()`——`<StrictMode>`（`main.tsx` 已掛）在
   * 開發模式下會把 updater 函式**呼叫兩次**以偵測不純的更新邏輯，`shift()`
   * 因此被呼叫兩次、佇列裡排在中間的那一則被無聲丟掉，只有第二次呼叫的
   * 結果被採用。改為只把**值**傳給 `setBanner`（不是函式），`current` 這個
   * 判斷改讀這支 ref——ref 永遠只被呼叫一次，不受 `<StrictMode>` 雙呼叫影響。
   */
  const bannerRef = useRef<BannerItem | null>(null);

  const shift = useCallback(() => {
    const next = queue.current.shift() ?? null;
    bannerRef.current = next;
    setBanner(next);
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
      // ⚠️ 讀 bannerRef 而非把函式傳給 setBanner（見該 ref 的說明）：只有目前
      // 沒有橫幅在顯示才從佇列拿一個出來，且只呼叫一次 shift()。
      if (bannerRef.current === null) {
        const next = queue.current.shift() ?? null;
        if (next !== null) {
          bannerRef.current = next;
          setBanner(next);
        }
      }
    }
  }, [audience, token]);

  /**
   * 401（後端不認這支 token）與其餘錯誤（網路抖動、5xx）分開處理（審查發現的
   * Important 4）：brief 與第一版修正的 `.catch(() => undefined)` 對所有例外
   * 一視同仁地靜默吞掉。web 裡其餘六支會打網路的模組全部接了
   * `session/useSignOutOnAuthError.ts`（P3 全分支審查訂下的架構結論，12 §4）
   * ——本 hook 是唯一的例外。401 最常見的觸發情境：家屬按「重新產生長輩綁定
   * 碼」（後端撤銷長輩全部 token）之後，長輩若停在對講機畫面不說話，
   * `useTalk` 的 401 判定掛在 `postTurn` 的 catch、觸發不到；若沒有其他畫面
   * 正在打後端，這支輪詢就是**唯一**還在打的請求，會每 `intervalMs` 收到一次
   * 註定失敗的 401、完全靜默丟棄，長輩畫面上不會有任何提示。網路抖動、5xx
   * 仍然完全靜默（通知是加分項，不該在畫面上留紅字）。
   */
  const handlePollError = useCallback(
    (exc: unknown) => {
      if (exc instanceof ApiError && exc.status === 401) {
        onTokenRevoked?.();
      }
    },
    [onTokenRevoked],
  );

  /**
   * 換人（audience 或 token 換掉，含登出＝token 變 ""）：橫幅與未讀徽章立刻
   * 歸零，不讓上一位使用者的殘留畫面留到新的這個人身上（審查發現的
   * Important 3：原本只歸零 `banner`，`unread` 沒有——登出後 `poll()` 因
   * `!token` 直接 return，`unread` 因此會停在上一位使用者的數字上，直到
   * 下一位使用者的第一輪輪詢才會被蓋掉；現在兩者一起歸零）。
   *
   * ⚠️ 這段刻意寫成「render 期間比對＋調整」（React 官方文件「Adjusting some
   * state when a prop changes」的既定寫法），不是 `useEffect`：改在 `useEffect`
   * 裡直接呼叫 `setBanner` 會先掛著上一位使用者的殘留橫幅多畫一次畫面、下一輪
   * render 才收掉（`react-hooks/set-state-in-effect` 擋下的正是這種會多一輪
   * cascading render 的寫法）。`lastSession` 只用來偵測「這一輪的 audience／token
   * 跟上一輪比對是否換了」，一旦換了就在同一次 render 內把 `banner`／`unread`
   * 歸零，使用者不會看到殘留橫幅或舊未讀數先閃一下才消失。
   *
   * ⚠️ 佇列／游標（`queue`／`shownUpTo`／`sessionRef`／`bannerRef`）不能放在
   * 這裡一起歸零：這幾個是 ref，`react-hooks/refs` 不准在 render 期間讀寫 ref
   * （會讓 React 判斷「這個元件要不要更新」的邏輯跟著亂掉）。改放到下面那顆
   * 只碰 ref、完全不呼叫任何 state setter 的獨立 `useEffect`。
   */
  const [lastSession, setLastSession] = useState({ audience, token });
  if (lastSession.audience !== audience || lastSession.token !== token) {
    setLastSession({ audience, token });
    setBanner(null);
    setUnread(0);
  }

  // 上面那段的 ref 版本：佇列／游標／「現在是誰」／橫幅鏡射都在這裡歸零，
  // 讓「第一次不補播歷史」對新的這個人同樣成立（一律從 0 起跳，不讀已讀
  // 水位，見檔頭 brief 缺陷 2）。effect 本身完全不呼叫任何 state setter。
  useEffect(() => {
    sessionRef.current = { audience, token };
    queue.current = [];
    shownUpTo.current = 0;
    bannerRef.current = null;
  }, [audience, token]);

  // bannerRef 與 banner 狀態同步（見該 ref 的說明）：`shift()` 已經會同步
  // 更新它，這裡是保險——`banner` 若未來透過其他路徑（如上方 render 期間
  // 比對的 `setBanner(null)`）改變，也要讓 `poll()` 讀到最新值。
  useEffect(() => {
    bannerRef.current = banner;
  }, [banner]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    /**
     * ⚠️ **審查發現的 Important 2（2026-08-01）**：非活動欄再度可見時，若不
     * 重設 `shownUpTo`，隱藏期間後端累積的每一則通知都會被 `pickNewItems`
     * 判定為「新的」而一次性補播出來——一則 3.5 秒，`QUEUE_MAX`（20）上限下
     * 最壞連播 70 秒。這正是本檔反覆稱為「展示現場最尷尬的失敗」的那件事，
     * 只是從「一進站」搬到了「切回來」，且檔頭 `:62-65`（已一併更正）原本誤
     * 宣稱不會發生。切回可見的第一輪要跟掛載時一樣，只重建基準、不補播歷史
     * ——同一套「brief 缺陷 2」語意。
     *
     * 只重設 `shownUpTo`，不動 `queue`／`banner`：隱藏期間本來就不會有新項目
     * 進佇列（整條 effect 早退），既有的橫幅與佇列狀態不受影響。
     */
    if (visible && !wasVisibleRef.current) {
      shownUpTo.current = 0;
    }
    wasVisibleRef.current = visible;

    // ⚠️ `!visible` 同 `!token` 一併擋掉：非活動欄（窄螢幕頁籤模式下被 CSS
    // `hidden` 蓋住的那一欄）整段跳過，連分頁可見性監聽器都不註冊——切回來時
    // 這條 effect 會因 `visible` 進了依賴陣列而重新掛一次，`run()` 立刻補一輪，
    // 不必等下一次輪詢間隔（與相機／麥克風切走即收、切回即恢復同一種寫法）。
    if (!token || !visible) return;
    let alive = true;
    const run = () => {
      void poll().catch(handlePollError);
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
  }, [poll, token, intervalMs, reloadSignal, handlePollError, visible]);

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

  return {
    banner,
    unread,
    dismiss: shift,
    reload: () => void poll().catch(handlePollError),
  };
}
