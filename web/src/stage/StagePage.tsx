/**
 * 雙欄舞台（spec §5.3、§9）。
 *
 * 寬螢幕左右並排（展示當天的主要形態：組員代操、投影給廠商看）；
 * 窄螢幕上下擇一顯示、頂部以頁籤切換（組員自己拿手機測試時用）。
 *
 * ⚠️ 兩欄各自持有獨立的 session（見 session/createSessionContext）。
 * 兩個 Provider 都掛在最外層而不是各掛在自己那一欄裡面——跨欄連動（家屬端操作
 * 完立刻叫長輩端重載、長輩／家屬端的通知輪詢）需要兩邊都在同一棵樹底下。
 *
 * ⚠️ **拆成 `StagePage`（掛 Provider）與 `StageBody`（用 Provider）兩層**（P4
 * Task 4）：通知輪詢要讀兩欄各自的 `session.token`，而 session 的讀取
 * （`ElderSession.useSession()`／`GuardianSession.useSession()`）必須發生在對應
 * Provider **內部**——合成一層直接在 `StagePage` 裡呼叫會擲出「必須在 Provider
 * 之內使用」，那個錯誤訊息是 P1 建立 `createSessionContext` 時刻意寫清楚的，這裡
 * 是它第一次真的派上用場。
 *
 * ⚠️ **跨欄連動有兩條不同的線**（P4 Task 3／4）：一條是 `notify/bus.ts` 的事件
 * 匯流排（只送「有事發生了」的訊號，不搬資料，這裡接上通知輪詢的
 * `reloadSignal`）；另一條是這裡的 `prefilledCode`／`sendCodeToElder`（直接搬
 * 一個字串——家屬產生的綁定碼），因為它就是要展示的資料本身，不是「叫對方去
 * 拉」。兩條線刻意分開：搬資料的需求只有這一種，不需要為它把兩欄的型別與快取
 * 綁在一起。
 */

import { memo, useCallback, useEffect, useRef, useState } from "react";

import { type ElderCodeDelivery } from "@/elder/BindScreen";
import { ElderApp } from "@/elder/ElderApp";
import { GuardianApp } from "@/guardian/GuardianApp";
import { NotificationBanner } from "@/notify/NotificationBanner";
import { useStageEvent } from "@/notify/bus";
import { detectOs, type PhoneOs } from "@/notify/osStyle";
import { useNotificationFeed } from "@/notify/useNotificationFeed";
import { ElderSession, GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";

import { PhoneFrame } from "./PhoneFrame";

type Pane = "elder" | "guardian";

/**
 * 兩欄並排的斷點。
 *
 * ⚠️ **這個數字與版面的 `lg:` 前綴是同一件事的兩種寫法**（`lg:hidden` 的頁籤、
 * `lg:grid-cols-2` 的兩欄、`lg:block` 的非活動欄）——Tailwind 的 `lg` 是 1024
 * **CSS px**。改版面就要改這裡，反之亦然；對不上的後果見 `useIsWideScreen`。
 */
const WIDE_SCREEN_QUERY = "(min-width: 1024px)";

/**
 * 現在是不是「兩欄同時看得到」的寬螢幕。
 *
 * ⚠️ **為什麼需要它**（全分支審查的 Important 2）：`elderVisible` 原本直接寫
 * `pane === "elder"`，理由是「寬螢幕沒有任何 UI 能把 `pane` 撥走（頁籤本身
 * `lg:hidden`），所以 `pane` 只可能在窄螢幕被撥走」。那個推論漏掉了**寬窄本身會變**
 * ——組員把視窗縮窄、或按 Ctrl+ 放大投影字級（Tailwind 的 `lg` 是 CSS px，縮放直接
 * 改變它）→ 頁籤出現 → 點「家屬端」→ 再放大視窗／縮回字級 → 兩欄又同時可見，而
 * `pane` 仍是 `"guardian"`。此時長輩欄看起來完全正常（`useTalk` 的 cleanup 把字幕
 * 重設回「按住下面的麥克風說話」、avatar 是 😊），但麥克風、播放器與長連線全被收掉
 * 了：按下去只會顯示「麥克風打不開，請再按一次試試看。」，再按一次還是一樣，而
 * `lg` 以上頁籤是 `display:none`——**畫面上不存在任何能把 `pane` 撥回來的 UI**。
 * 而投影機上的那一欄，正是所有人在看的那一欄。
 *
 * Task 7 當時把這條列為「已接受取捨」，理由是「失效良性、可自行恢復（再按一次
 * 掃描）」；Task 8 把麥克風接上同一個開關之後，那個理由不再成立。P4 Task 4 再把
 * 兩欄的通知輪詢也接上同一個開關（`elderVisible`／`guardianVisible`）——原理相同：
 * 非活動欄只是被 CSS `hidden` 蓋住，計時器與 `display:none` 無關，不擋的話會一直
 * 打到分頁關閉為止。
 *
 * ⚠️ 選 `matchMedia` 而不是聽 `resize` 讀 `innerWidth`：斷點的判定要與 CSS 用的是
 * 同一套（含縮放、含 `zoom` 造成的 CSS px 變化），自己算像素一定會漂。
 * ⚠️ jsdom 沒有 `window.matchMedia`（實測 `typeof` 是 `undefined`），拿不到就當成
 * 「不是寬螢幕」——那正好是頁籤模式的語意，測試環境因此維持原本的行為。
 */
function useIsWideScreen(): boolean {
  const [isWide, setIsWide] = useState(() => window.matchMedia?.(WIDE_SCREEN_QUERY).matches ?? false);

  useEffect(() => {
    const query = window.matchMedia?.(WIDE_SCREEN_QUERY);
    if (!query) {
      return;
    }
    const update = () => setIsWide(query.matches);
    // 掛載與訂閱之間仍可能已經變過（首次繪製到 effect 執行中間隔了一次版面計算），
    // 先對一次答案再開始聽。
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return isWide;
}

/**
 * ⚠️ `memo` 是刻意的：這裡不收任何 props，父層（`Demo`）每十秒一次的運營狀態
 * 輪詢會 setState 一個新物件而整棵重繪，沒有 `memo` 的話 `StagePage` 會跟著
 * 白白重繪一次。P1 的佔位元件無感，但 P2／P3 接上表單與對講機之後，那是長輩
 * 正在講話的那棵樹每十秒被無條件重繪——不要為了「省輪詢」改成上舞台後停止
 * 輪詢，那會讓使用者按上一頁回開場時看到「正在確認服務狀態…」（見 App.tsx 對
 * `useDemoStatus` 那段註解，是剛修好的 I2）。
 *
 * ⚠️ `StagePage` 本身只掛兩個 Provider、不含任何會變動的狀態，`StageBody` 才是
 * 真正的舞台內容——`memo` 擋住的是「父層重繪 → `StagePage` 重新協調」這一層，
 * `StageBody` 因此也不會跟著白畫一次（它只從自己的 state／context 觸發重繪）。
 */
export const StagePage = memo(function StagePage() {
  return (
    <ElderSession.Provider>
      <GuardianSession.Provider>
        <StageBody />
      </GuardianSession.Provider>
    </ElderSession.Provider>
  );
});

function StageBody() {
  const [pane, setPane] = useState<Pane>("elder");
  const [os, setOs] = useState<PhoneOs>(() => detectOs(navigator.userAgent));
  const isWide = useIsWideScreen();

  const elder = ElderSession.useSession();
  const guardian = GuardianSession.useSession();

  // 家屬欄產生的綁定碼（新建長輩／重新產生綁定碼）直接送到長輩欄（spec W-15
  // 內測捷徑，接收端見 `elder/BindScreen.tsx`）：省去在同一個瀏覽器分頁裡「拿
  // 一欄的相機去掃另一欄螢幕上的 QR」這種不切實際的操作。
  //
  // ⚠️ **全分支審查修正（Important 1）**：這是一次性**事件**，不是單純的值
  // ——`seq` 每次送出都要遞增（`sendSeqRef` 這支 ref 不放進 state，純粹用來
  // 產生單調遞增的序號，本身不驅動任何畫面）。若只送 `code` 字串本身，同一組
  // 碼被家屬重複送出（例如長輩自己把欄位改壞、家屬切回去再按一次同一顆鈕）會
  // 因為字串沒變而被 `BindScreen` 判斷成「沒有變化」而略過同步。詳見
  // `elder/BindScreen.tsx` 的 `ElderCodeDelivery` 型別說明。
  const [prefilledCode, setPrefilledCode] = useState<ElderCodeDelivery | undefined>(undefined);
  const sendSeqRef = useRef(0);

  // ⚠️ 審查發現的 Critical：長輩欄按下「掃描 QR 碼」後，若在窄螢幕切到
  // 「家屬端」頁籤，非活動欄只是被 CSS `hidden` 蓋住——元件仍掛著，
  // `MediaStream` 軌道與 `display:none` 無關，相機會一直開到分頁關閉為止。
  // 把「這一欄現在看得到嗎」算出來往下傳，讓 `BindScreen` 自己決定要不要
  // 停止掃描（見該檔說明），而不是卸載這一欄（卸載會丟掉長輩打到一半的
  // 號碼）。P4 Task 4 把兩欄的通知輪詢也接上同一個值，理由相同。
  //
  // ⚠️ 這個值必須反映**真實可見性**，不是 `pane` 狀態：寬螢幕時 `lg:block` 讓兩欄
  // 同時可見、與 `pane` 無關，而寬窄本身會在使用中改變（縮放視窗、Ctrl+ 放大字級）。
  // 只看 `pane` 的話，會出現「畫面看起來完全正常、麥克風卻永遠打不開，而且沒有任何
  // UI 能把它撥回來」的死路——詳見 `useIsWideScreen` 的說明。
  const elderVisible = isWide || pane === "elder";
  /**
   * 家屬欄的對稱版本（P4 Task 4 新增）。
   *
   * ⚠️ Task 3 審查當時 grep 確認家屬欄沒有任何長生命週期資源（相機／麥克風／
   * 長連線），缺這條線不影響什麼；接上通知輪詢（兩秒一次的計時器）之後這條線
   * 變成真實需求——同一種坑（非活動欄只是 CSS `hidden`、元件仍掛著，計時器
   * 繼續打到分頁關閉）第五次發生，只是換了個資源種類（網路請求，不是硬體）。
   */
  const guardianVisible = isWide || pane === "guardian";

  // ⚠️ 窄螢幕頁籤模式下另一欄不在畫面上，光是把碼傳下去，家屬按下去什麼都
  // 看不到（連動了也像沒動一樣）——所以連動的同時把頁籤切回長輩端，這正是這
  // 條內測捷徑要做給人看的效果（「你看，長輩那邊出現了」）。寬螢幕兩欄本來就
  // 都看得見，`setPane` 在那裡是無害的（下次縮窄視窗時頁籤會自然停在長輩端）。
  function sendCodeToElder(code: string) {
    sendSeqRef.current += 1;
    setPrefilledCode({ code, seq: sendSeqRef.current });
    setPane("elder");
  }

  // 家屬寫入之後（新增長輩、編輯排程）立刻叫長輩端重拉一次通知，不等下一次輪詢。
  //
  // ⚠️ **不要以為「按下新增排程，左欄就會跳出橫幅」**（2026-08-01 全分支審查更正
  // 的假前提）：`app_notifications` 全部由排程器／危急事件寫入，建立排程本身一則
  // 都不會產生。這條線的真實效果與保留理由見 `notify/bus.ts` 檔頭。
  const guardianWrote = useStageEvent("guardian-wrote");

  /**
   * 長輩欄通知輪詢收到 401 時遞增的序號，交給 `ElderApp` 的 `tokenRevokedSeq`
   * （見該檔說明）。
   *
   * ⚠️ **審查發現的 Important 1（2026-08-01）**：這裡原本直接呼叫 `elder.signOut()`，
   * 但那樣會**搶在** `elder/useTalk.ts` 既有的 401 判定（掛在 `postTurn` 的
   * catch，只有長輩按下麥克風講話才會觸發、才會顯示「家人幫您重新設定了…」）
   * 前面把人靜默登出——輪詢每 2 秒打一次，長輩若停在對講機不說話，輪詢一定先到。
   * 失效情境（展示主路徑）：家屬按「重新產生長輩綁定碼」→ 長輩停在對講機沒說話
   * → 2 秒內被輪詢的 401 靜默登出、配對畫面上一個字的解釋都沒有。改為只遞增
   * 序號、不直接呼叫 `signOut()`，讓 `ElderApp` 自己的 `loseSession` 統一處理
   * signOut＋說明兩件事，兩條 401 出口殊途同歸。
   */
  const [elderTokenRevokedSeq, setElderTokenRevokedSeq] = useState(0);
  const elderTokenRevokedSeqRef = useRef(0);

  /**
   * ⚠️ **全分支審查發現的 Minor 5（2026-08-01）——必須是穩定參考**：這裡原本是
   * 寫在 `useNotificationFeed({...})` 裡的行內箭頭函式，每次 render 都是一顆新
   * 的函式，於是 hook 內的 `handlePollError`（`useCallback` 相依 `onTokenRevoked`）
   * 跟著換身分、輪詢 effect 的相依陣列跟著變 → **`StageBody` 每重繪一次，長輩欄
   * 的輪詢 effect 就被拆掉重建並立刻 `run()` 一輪**，`setInterval` 也重新起算。
   * 家屬欄那邊傳的是 `guardian.signOut`（`createSessionContext` 裡的
   * `useCallback(..., [])`，穩定），所以只有長輩欄會這樣，兩欄接線原本不對稱。
   *
   * ⚠️ 這不只是「多打幾次請求」：輪詢自己的 `setUnread` 就會讓 `StageBody` 重繪，
   * 於是「輪詢 → 重繪 → 重建 effect → 再輪詢」會連鎖跑好幾輪才收斂（實測：一次
   * `render()` 之後長輩欄打了 **4** 次請求，而不是 1 次），中間那幾輪還會把
   * 「切回前景只重建基準」這類以輪詢次數為前提的行為整個打亂。
   */
  const handleElderTokenRevoked = useCallback(() => {
    elderTokenRevokedSeqRef.current += 1;
    setElderTokenRevokedSeq(elderTokenRevokedSeqRef.current);
  }, []);

  const elderFeed = useNotificationFeed({
    audience: "elder",
    token: elder.session?.token ?? "",
    reloadSignal: guardianWrote,
    visible: elderVisible,
    onTokenRevoked: handleElderTokenRevoked,
  });
  const guardianFeed = useNotificationFeed({
    audience: "guardian",
    token: guardian.session?.token ?? "",
    visible: guardianVisible,
    // ⚠️ 家屬欄沒有對應 `ElderApp::signedOutNotice` 那種「被誰登出」的說明需求
    // （家屬帳密是自己設定的，401 只代表 token 過期／別處登出所有裝置），故
    // 直接呼叫 `signOut()` 已足夠——`GuardianApp` 的登入守衛會自動導回登入畫面。
    onTokenRevoked: guardian.signOut,
  });

  return (
    <main className="min-h-dvh bg-background p-4 lg:p-8">
      <div className="mx-auto mb-4 flex w-full max-w-5xl items-center justify-between gap-2">
        {/* 窄螢幕的切換頁籤。寬螢幕兩欄都看得到，不需要它。 */}
        <div role="tablist" className="flex flex-1 gap-2 lg:hidden">
          {(
            [
              ["elder", strings.stage.elderTab],
              ["guardian", strings.stage.guardianTab],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              role="tab"
              aria-selected={pane === value}
              onClick={() => setPane(value)}
              className={`min-h-12 flex-1 rounded-2xl text-base font-bold transition-colors ${
                pane === value
                  ? "bg-primary text-white"
                  : "border border-line bg-surface text-ink-soft"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {/* 通知樣式手動切換鈕（P4 Task 4）：UA 只能給一個合理的預設，而展示時
            觀眾會想看兩種、投影用的筆電也只有一種 UA。兩欄共用同一個 `os`值，
            不再各欄寫死——展示時要看的是「同一套系統在兩種手機上的樣子」，
            兩邊各一種反而看不出差別。 */}
        <button
          type="button"
          aria-label={strings.stage.notificationStyle(os)}
          onClick={() => setOs((current) => (current === "ios" ? "android" : "ios"))}
          className="min-h-12 shrink-0 rounded-2xl border border-line bg-surface px-4 text-sm font-semibold text-ink-soft"
        >
          {strings.stage.notificationStyle(os)}
        </button>
      </div>

      <div className="mx-auto grid w-full max-w-5xl gap-8 lg:grid-cols-2">
        <div className={pane === "elder" ? "" : "hidden lg:block"}>
          <PhoneFrame
            title={strings.stage.elderTitle}
            os={os}
            notificationSlot={
              // size="big"：這張橫幅一旦被塞進長輩欄，恰好是長輩該讀的那句話
              // （如「提醒您：降血壓藥」），字級要守長輩端 22px 下限（見
              // `notify/NotificationBanner.tsx` 該 prop 的說明）。
              <NotificationBanner
                item={elderFeed.banner}
                os={os}
                onDismiss={elderFeed.dismiss}
                size="big"
              />
            }
            // ⚠️ 必須與上面那則橫幅來自同一個 `banner`（2026-08-01）：視覺（紅色，
            // 由 `NotificationBanner` 讀 `item.severity`）與宣告強度（`role="alert"`／
            // `aria-live="assertive"`，由 `PhoneFrame` 讀這個 prop）是兩條各自
            // 獨立的路徑，缺一就只有一半的人分得出危急警報。
            notificationSeverity={elderFeed.banner?.severity}
          >
            <ElderApp
              visible={elderVisible}
              prefilledCode={prefilledCode}
              unread={elderFeed.unread}
              tokenRevokedSeq={elderTokenRevokedSeq}
            />
          </PhoneFrame>
        </div>
        <div className={pane === "guardian" ? "" : "hidden lg:block"}>
          <PhoneFrame
            title={strings.stage.guardianTitle}
            os={os}
            notificationSlot={
              <NotificationBanner item={guardianFeed.banner} os={os} onDismiss={guardianFeed.dismiss} />
            }
            // 家屬欄同理（見長輩欄的說明）——而且展示最有感染力的那一刻，紅色
            // 警報正是滑進**這一欄**。
            notificationSeverity={guardianFeed.banner?.severity}
          >
            <GuardianApp onSendCodeToElder={sendCodeToElder} unread={guardianFeed.unread} />
          </PhoneFrame>
        </div>
      </div>
    </main>
  );
}
