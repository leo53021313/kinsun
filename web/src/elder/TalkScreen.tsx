/**
 * 對講機主畫面。適老化（✅ D-48）：字大、對比高、觸控目標超大。
 *
 * ⚠️ 麥克風鍵用 `pointerdown`／`pointerup`／`pointercancel` 而非 mouse／touch
 * 兩套：一套涵蓋滑鼠與觸控。`pointercancel` 不可省——手指滑出按鈕範圍、系統
 * 跳出對話框都會送它，漏接的話狀態機會停在「錄音中」而長輩已經放開了。
 *
 * ⚠️ 狀態與副作用全在 `useTalk`，這裡只讀值、只把手勢轉交出去。
 */

import { useEffect, useId, useRef, useState } from "react";

import { strings } from "@/strings";
import { Button } from "@/ui/Button";

import { BearStage } from "./BearStage";
import { useTalk } from "./useTalk";

export function TalkScreen(props: {
  token: string;
  unread: number;
  /** 這一欄目前是否真的看得見（窄螢幕頁籤模式）。轉交給 `useTalk`，見該檔說明。 */
  visible?: boolean;
  onOpenNotifications: () => void;
  onLogout: () => void;
  onBindingLost: () => void;
  /** 後端不認這支 token（401）。與 403 分開的理由見 `useTalk` 該 prop 的說明。 */
  onTokenRevoked: () => void;
}) {
  const { visible = true } = props;
  const talk = useTalk({
    token: props.token,
    visible,
    onBindingLost: props.onBindingLost,
    onTokenRevoked: props.onTokenRevoked,
  });
  const disabled = !talk.micReady || talk.avatar === "thinking";

  // ⚠️ 登出要二次確認：只靠家人給的綁定碼配對、家屬還沒替他設過帳密的長輩，
  // 一旦登出就**自己回不來**——他要再跟家人要一組碼。刪一筆排程都要確認了，
  // 這個更要（`ElderDetailScreen` 的「重新產生綁定碼」是同一套作法與理由）。
  //
  // ⚠️ 用畫面內的確認列而非瀏覽器的 `confirm()`：confirm 會鎖住整個分頁，雙欄
  // 同時存在時另一欄連按都按不了。
  const [isConfirmingLogout, setIsConfirmingLogout] = useState(false);
  const confirmHeadingId = useId();
  const confirmRef = useRef<HTMLDivElement | null>(null);

  // 確認列一出現就把焦點移進去：它在 DOM 裡但焦點沒過去的話，螢幕報讀軟體不會
  // 朗讀那句後果——而那句後果正是這顆按鈕存在的理由。
  useEffect(() => {
    if (isConfirmingLogout) {
      confirmRef.current?.focus();
    }
  }, [isConfirmingLogout]);

  return (
    <div className="flex h-full flex-col gap-4 p-5">
      <div className="flex items-center justify-between">
        <button
          type="button"
          aria-label={
            props.unread > 0
              ? strings.elderNotifications.bellWithUnread(props.unread)
              : strings.elderNotifications.bell
          }
          onClick={props.onOpenNotifications}
          // 56px：長輩手指粗又常戴老花，48px 的最小可觸控目標對他們仍偏小。
          className="relative flex size-14 items-center justify-center rounded-full border border-line bg-surface text-2xl"
        >
          <span aria-hidden>🔔</span>
          {props.unread > 0 ? (
            // 紅點只是給看得見的人的捷徑；真正的數字在上面的 aria-label 裡。
            // ⚠️ 字級仍受長輩端 22px 下限（`--text-elder-min`）約束——「捷徑」是給
            // **看得見的長輩**用的，14px 的數字他看不清，那條捷徑就不存在。圓點跟著
            // 放大到 32px 才裝得下（`leading-none` 讓它不被行高撐開）。`ElderApp`
            // 已於 P4 Task 4（2026-08-01）接上真正的輪詢結果（見該檔 `unread` prop）。
            <span
              aria-hidden
              className="absolute right-0 top-0 flex min-w-8 items-center justify-center rounded-full bg-danger px-1 text-elder-min font-bold leading-none text-white"
            >
              {props.unread > 9 ? "9+" : props.unread}
            </span>
          ) : null}
        </button>
        <button
          type="button"
          onClick={() => setIsConfirmingLogout(true)}
          disabled={isConfirmingLogout}
          // ⚠️ 長輩端可點擊目標一律 ≥56px、字級 ≥22px，次要按鈕也不例外
          //（brief 原始版本是 48px／16px，低於長輩端下限；Task 7 剛為同一件事
          // 修過 `BindScreen` 的次要導覽按鈕）。
          className="min-h-14 rounded-2xl px-4 text-elder-min text-ink-soft disabled:opacity-50"
        >
          {strings.talk.logout}
        </button>
      </div>

      {isConfirmingLogout ? (
        <div
          ref={confirmRef}
          tabIndex={-1}
          role="alertdialog"
          // ⚠️ 刻意**不**宣告 `aria-modal="true"`：那會讓螢幕報讀軟體把畫面其餘
          // 內容藏起來，但這裡沒有焦點陷阱、麥克風鍵仍然可以按——看得見的人與
          // 聽的人會拿到兩種不一樣的畫面。不用 `window.confirm` 是對的（它鎖住
          // 整個分頁，雙欄同時存在時另一欄連按都按不了），但那也代表不該宣稱
          // 自己是模態的。
          aria-labelledby={confirmHeadingId}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setIsConfirmingLogout(false);
            }
          }}
          className="flex flex-col gap-3 rounded-2xl border-2 border-danger bg-surface p-4"
        >
          <p id={confirmHeadingId} className="text-elder-min leading-relaxed text-ink">
            {strings.talk.logoutConfirmBody}
          </p>
          <div className="flex gap-2">
            <Button
              label={strings.talk.confirmLogoutButton}
              size="big"
              onClick={() => {
                setIsConfirmingLogout(false);
                props.onLogout();
              }}
            />
            <Button
              label={strings.talk.logoutCancel}
              variant="outline"
              size="big"
              onClick={() => setIsConfirmingLogout(false)}
            />
          </div>
        </div>
      ) : null}

      <div className="flex justify-center">
        <BearStage state={talk.avatar} />
      </div>

      {/* 回覆可捲動：短回覆置中、長回覆可上滑看完，字級不縮。
          role="status"：金孫講了什麼是這個畫面唯一的產出，讀螢幕的人不會自己
          去掃畫面找它；polite 語意不會打斷目前的朗讀。 */}
      <div className="flex min-h-0 flex-1 items-center overflow-y-auto">
        <p
          role="status"
          className="w-full text-center text-elder-big font-semibold leading-relaxed text-ink"
        >
          {talk.replyText}
        </p>
      </div>

      <button
        type="button"
        aria-label={strings.talk.pressToTalk}
        disabled={disabled}
        onPointerDown={(event) => {
          // ⚠️ 指標捕捉：滑鼠按住之後拖出按鈕範圍才放開時，`pointerup` 會送到
          // 別的元素上，我們的 `pressOut` 永遠不會被呼叫——手勢狀態機停在
          // 「錄音中」、麥克風指示燈一直亮著，而長輩早就放開了。捕捉之後，
          // `pointerup`／`pointercancel` 保證回到這顆按鈕。
          try {
            event.currentTarget.setPointerCapture(event.pointerId);
          } catch {
            // 舊瀏覽器或測試環境沒有這個 API。少一層保險而已，主要路徑不受影響。
          }
          talk.pressIn();
        }}
        onPointerUp={talk.pressOut}
        onPointerCancel={talk.pressOut}
        // 104px：與 App 的麥克風鍵同尺寸。用任意值而非新增設計 token——這是單一
        // 元件的尺寸，不是跨端共用的品牌值（`theme.css` 那一組要與 app 端逐一對齊）。
        // touch-none：不讓瀏覽器把「按住」判成捲動而把手勢搶走。
        // select-none：iOS 長按會跳出選字放大鏡，蓋住半個畫面。
        className={`mx-auto flex size-[104px] touch-none select-none items-center justify-center rounded-full text-5xl transition-colors ${
          talk.avatar === "listening" ? "bg-primary-pressed" : "bg-primary"
        } ${disabled ? "opacity-50" : ""}`}
      >
        <span aria-hidden>🎤</span>
      </button>
    </div>
  );
}
