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
                <ElderApp />
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
