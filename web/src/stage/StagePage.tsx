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

import { useState } from "react";

import { ElderSession, GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";

import { PhoneFrame } from "./PhoneFrame";

type Pane = "elder" | "guardian";

export function StagePage() {
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
                <ElderPanePlaceholder />
              </PhoneFrame>
            </div>
            <div className={pane === "guardian" ? "" : "hidden lg:block"}>
              <PhoneFrame title={strings.stage.guardianTitle} os="android">
                <GuardianPanePlaceholder />
              </PhoneFrame>
            </div>
          </div>
        </main>
      </GuardianSession.Provider>
    </ElderSession.Provider>
  );
}

/** P3 換成完整的長輩端。此處先佔位，讓版面與 session 接線可以先驗收。 */
function ElderPanePlaceholder() {
  const { session } = ElderSession.useSession();
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-elder-min text-ink-soft">
      {session ? session.display_name : "長輩端（尚未實作）"}
    </div>
  );
}

/** P2 換成完整的家屬端。 */
function GuardianPanePlaceholder() {
  const { session } = GuardianSession.useSession();
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-base text-ink-soft">
      {session ? session.display_name : "家屬端（尚未實作）"}
    </div>
  );
}
