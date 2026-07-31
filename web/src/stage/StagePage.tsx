/**
 * 雙欄舞台（spec §5.3）。
 *
 * 寬螢幕左右並排（展示當天的主要形態：組員代操、投影給廠商看）；
 * 窄螢幕上下擇一顯示、頂部以頁籤切換（組員自己拿手機測試時用）。
 *
 * ⚠️ 兩欄各自持有獨立的 session（見 session/createSessionContext）。
 * 兩個 Provider 都掛在最外層而不是各掛在自己那一欄裡面——P4 的跨欄連動
 * （家屬端操作完立刻叫長輩端重載）需要兩邊都在同一棵樹底下。
 *
 * ⚠️ **跨欄連動有兩條不同的線**（P4 Task 3）：一條是 `notify/bus.ts` 的事件匯
 * 流排（只送「有事發生了」的訊號，不搬資料，供 Task 4 接上通知輪詢的
 * `reloadSignal`）；另一條是這裡的 `prefilledCode`／`sendCodeToElder`（直接搬
 * 一個字串——家屬產生的綁定碼），因為它就是要展示的資料本身，不是「叫對方去
 * 拉」。兩條線刻意分開：搬資料的需求只有這一種，不需要為它把兩欄的型別與快取
 * 綁在一起。
 */

import { memo, useEffect, useRef, useState } from "react";

import { type ElderCodeDelivery } from "@/elder/BindScreen";
import { ElderApp } from "@/elder/ElderApp";
import { GuardianApp } from "@/guardian/GuardianApp";
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
 * 掃描）」；Task 8 把麥克風接上同一個開關之後，那個理由不再成立。
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
 */
export const StagePage = memo(function StagePage() {
  const [pane, setPane] = useState<Pane>("elder");
  const isWide = useIsWideScreen();
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
  // 號碼）。
  //
  // ⚠️ 這個值必須反映**真實可見性**，不是 `pane` 狀態：寬螢幕時 `lg:block` 讓兩欄
  // 同時可見、與 `pane` 無關，而寬窄本身會在使用中改變（縮放視窗、Ctrl+ 放大字級）。
  // 只看 `pane` 的話，會出現「畫面看起來完全正常、麥克風卻永遠打不開，而且沒有任何
  // UI 能把它撥回來」的死路——詳見 `useIsWideScreen` 的說明。
  //
  // ⚠️ **給 Task 4 的接線提醒（全分支審查 Minor）**：目前只有 `elderVisible`，
  // 沒有對稱的 `guardianVisible`。本輪（P4 Task 3）審查已 grep 確認家屬欄目前
  // 沒有任何長生命週期資源（相機／麥克風／長連線），所以缺這條線不會造成資源
  // 洩漏；但 Task 4 要把 `notify/useNotificationFeed.ts`（兩秒輪詢）接進家屬欄
  // 時，這條線就會變成真實需求——同一種坑 `elderVisible` 已經在 `BindScreen`／
  // `TalkScreen` 修過（窄螢幕頁籤模式下非活動欄只是 CSS `hidden`、元件仍掛著，
  // 輪詢會繼續打）。算法應與 `elderVisible` 對稱：
  // `const guardianVisible = isWide || pane === "guardian";`。
  const elderVisible = isWide || pane === "elder";

  // ⚠️ 窄螢幕頁籤模式下另一欄不在畫面上，光是把碼傳下去，家屬按下去什麼都
  // 看不到（連動了也像沒動一樣）——所以連動的同時把頁籤切回長輩端，這正是這
  // 條內測捷徑要做給人看的效果（「你看，長輩那邊出現了」）。寬螢幕兩欄本來就
  // 都看得見，`setPane` 在那裡是無害的（下次縮窄視窗時頁籤會自然停在長輩端）。
  function sendCodeToElder(code: string) {
    sendSeqRef.current += 1;
    setPrefilledCode({ code, seq: sendSeqRef.current });
    setPane("elder");
  }

  return (
    <ElderSession.Provider>
      <GuardianSession.Provider>
        <main className="min-h-dvh bg-background p-4 lg:p-8">
          {/* 窄螢幕的切換頁籤。寬螢幕兩欄都看得到，不需要它。 */}
          <div role="tablist" className="mx-auto mb-4 flex w-full max-w-sm gap-2 lg:hidden">
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

          <div className="mx-auto grid w-full max-w-5xl gap-8 lg:grid-cols-2">
            <div className={pane === "elder" ? "" : "hidden lg:block"}>
              <PhoneFrame title={strings.stage.elderTitle} os="ios">
                <ElderApp visible={elderVisible} prefilledCode={prefilledCode} />
              </PhoneFrame>
            </div>
            <div className={pane === "guardian" ? "" : "hidden lg:block"}>
              <PhoneFrame title={strings.stage.guardianTitle} os="android">
                <GuardianApp onSendCodeToElder={sendCodeToElder} />
              </PhoneFrame>
            </div>
          </div>
        </main>
      </GuardianSession.Provider>
    </ElderSession.Provider>
  );
});
