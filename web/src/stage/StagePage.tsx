/**
 * 雙欄舞台（spec §5.3）。
 *
 * 寬螢幕左右並排（展示當天的主要形態：組員代操、投影給廠商看）；
 * 窄螢幕上下擇一顯示、頂部以頁籤切換（組員自己拿手機測試時用）。
 *
 * ⚠️ 兩欄各自持有獨立的 session（見 session/createSessionContext）。
 * 兩個 Provider 都掛在最外層而不是各掛在自己那一欄裡面——P4 的跨欄連動
 * （家屬端操作完立刻叫長輩端重載）需要兩邊都在同一棵樹底下。
 */

import { memo, useState } from "react";

import { ElderApp } from "@/elder/ElderApp";
import { GuardianApp } from "@/guardian/GuardianApp";
import { ElderSession, GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";

import { PhoneFrame } from "./PhoneFrame";

type Pane = "elder" | "guardian";

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

  // ⚠️ 審查發現的 Critical：長輩欄按下「掃描 QR 碼」後，若在窄螢幕切到
  // 「家屬端」頁籤，非活動欄只是被 CSS `hidden` 蓋住——元件仍掛著，
  // `MediaStream` 軌道與 `display:none` 無關，相機會一直開到分頁關閉為止。
  // 把「這一欄現在看得到嗎」算出來往下傳，讓 `BindScreen` 自己決定要不要
  // 停止掃描（見該檔說明），而不是卸載這一欄（卸載會丟掉長輩打到一半的
  // 號碼）。
  //
  // `pane === "elder"` 在寬螢幕（`lg` 以上）看似不精確——`lg:block` 會讓
  // 兩欄同時可見，與 `pane` 狀態無關——但頁籤按鈕本身也是 `lg:hidden`
  // （見下方 `tablist`），寬螢幕下沒有任何 UI 能把 `pane` 從初始值 `"elder"`
  // 撥走，故 `pane` 只可能在使用者親手切過頁籤（也就是已經在窄螢幕）之後
  // 才會變成 `"guardian"`；那個當下長輩欄確實是被 `hidden` 蓋住、沒有
  // `lg:block` 生效。`pane === "elder"` 因此是這個互動模型下的準確訊號。
  const elderVisible = pane === "elder";

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
                <ElderApp visible={elderVisible} />
              </PhoneFrame>
            </div>
            <div className={pane === "guardian" ? "" : "hidden lg:block"}>
              <PhoneFrame title={strings.stage.guardianTitle} os="android">
                <GuardianApp />
              </PhoneFrame>
            </div>
          </div>
        </main>
      </GuardianSession.Provider>
    </ElderSession.Provider>
  );
});
