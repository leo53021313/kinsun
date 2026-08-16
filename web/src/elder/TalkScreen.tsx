/**
 * 對講機主畫面。適老化（✅ D-48）：字大、對比高、觸控目標超大。
 *
 * ## 版面＝四層絕對定位，一屏內不捲（W3b）
 *
 * 接手指示規則 2：「每個畫面一屏內不捲動——長輩不一定知道要滑」。原本這裡是
 * `flex h-full flex-col` 的直欄，內容一多就把主鍵擠出畫面，而外框還會整頁捲。
 * 改成與 App 相同的四層：
 *
 * ```
 * 頁首（z40，top 66）→ 角色舞台（z10，top 140，固定）→ 內容層（z20，貼底往上長）
 *                                                    → 主鍵（z30，bottom 40）
 * ```
 *
 * ⚠️ **設計稿的 y 座標以裝置畫面頂端為原點**（App 的對講機頁沒有包 SafeAreaView，
 * 狀態列是 OS 疊在 app 之上），而 `PhoneFrame` 的內容區已經扣掉 54px 狀態列與
 * 34px home indicator。下面三個常數就是這個換算，寫成算式而不是換算後的數字，
 * 不然下一個人看到 12／86／6 會不知道它們跟設計稿的 66／140／40 是同一組值。
 *
 * ⚠️ **角色舞台永不縮放或位移**（規則 3）。需要空間時讓位的是麥克風主鍵
 * （132 → 72）與回話卡，不是角色。
 *
 * ⚠️ **系統字級放大的例外**：設計稿寫的是 RN 的 `fontScale ≥ 1.5 時只有內容層可捲」。
 * 網頁沒有 `fontScale` 這個 API——瀏覽器的等價物是使用者調大預設字級或縮放，效果是
 * 文字撐高。所以這裡改用等價的做法：只有回話卡內文設 `max-height` ＋ `overflow-y-auto`，
 * 撐不下時就它自己捲，頁首、角色與主鍵仍然固定。行為與設計意圖一致，而且不必去
 * 猜一個瀏覽器量不到的倍率。
 *
 * ⚠️ 麥克風鍵用 `pointerdown`／`pointerup`／`pointercancel` 而非 mouse／touch
 * 兩套：一套涵蓋滑鼠與觸控。`pointercancel` 不可省——手指滑出按鈕範圍、系統
 * 跳出對話框都會送它，漏接的話狀態機會停在「錄音中」而長輩已經放開了。
 *
 * ⚠️ 狀態與副作用全在 `useTalk`，這裡只讀值、只把手勢轉交出去。`collapsed` 是本層
 * 自己的呈現旗標（與 App 一致，放在畫面而不是狀態機裡），不是新的視覺狀態。
 */

import { useEffect, useRef, useState } from "react";

import { strings } from "@/strings";
import { PHONE_HOME_INDICATOR_H, PHONE_STATUS_BAR_H } from "@/stage/PhoneFrame";
import { Button } from "@/ui/Button";

import { BearStage } from "./BearStage";
import { MicIcon, TalkStatusIcon } from "./TalkIcons";
import { appendTurn } from "./todayLog";
import { useTalk, type AvatarState } from "./useTalk";

/** 設計稿座標（以裝置畫面頂端／底端為原點）換算成 PhoneFrame 內容區的座標。 */
const HEADER_TOP = 66 - PHONE_STATUS_BAR_H;
const STAGE_TOP = 140 - PHONE_STATUS_BAR_H;
const MIC_BOTTOM = 40 - PHONE_HOME_INDICATOR_H;

/** 主鍵兩種尺寸：主要態 132、阿白說話時的次要態 72（`theme.css` 的長輩端 token）。 */
const MIC_SIZE = 132;
const MIC_SIZE_SMALL = 72;

/** 內容層的底距：讓開主鍵那一塊。說話時主鍵縮小且標籤改橫排，讓出來的空間更多。 */
const CONTENT_BOTTOM = MIC_BOTTOM + MIC_SIZE + 34 + 16;
const CONTENT_BOTTOM_SPEAKING = MIC_BOTTOM + MIC_SIZE_SMALL + 16;

/** 收合膠囊只留一行：前綴＋回答前 12 字＋刪節號。 */
function collapsedSummary(reply: string): string {
  const body = reply.trim();
  const head = body.slice(0, 12);
  return `${strings.talk.collapsedPrefix}${head}${body.length > 12 ? "…" : ""}`;
}

function actionLabel(state: AvatarState): string {
  if (state === "speaking") return strings.talk.actions.waitWhileSpeaking;
  if (state === "listening") return strings.talk.actions.listening;
  if (state === "thinking") return strings.talk.actions.thinking;
  if (state === "error") return strings.talk.actions.error;
  return strings.talk.actions.start;
}

export function TalkScreen(props: {
  token: string;
  unread: number;
  /** 這一欄目前是否真的看得見（窄螢幕頁籤模式）。轉交給 `useTalk`，見該檔說明。 */
  visible?: boolean;
  onOpenNotifications: () => void;
  /** 進「之前聊過的」（頁首左側 60dp 圓鈕）。 */
  onOpenHistory: () => void;
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
  const isSpeaking = talk.avatar === "speaking";

  // ⚠️ 登出要二次確認：只靠家人給的綁定碼配對、家屬還沒替他設過帳密的長輩，
  // 一旦登出就**自己回不來**——他要再跟家人要一組碼。刪一筆排程都要確認了，
  // 這個更要（`ElderDetailScreen` 的「重新產生綁定碼」是同一套作法與理由）。
  //
  // ⚠️ 用畫面內的確認列而非瀏覽器的 `confirm()`：confirm 會鎖住整個分頁，雙欄
  // 同時存在時另一欄連按都按不了。
  const [isConfirmingLogout, setIsConfirmingLogout] = useState(false);
  const confirmRef = useRef<HTMLDivElement | null>(null);

  // 確認列一出現就把焦點移進去：它在 DOM 裡但焦點沒過去的話，螢幕報讀軟體不會
  // 朗讀那句後果——而那句後果正是這顆按鈕存在的理由。
  useEffect(() => {
    if (isConfirmingLogout) {
      confirmRef.current?.focus();
    }
  }, [isConfirmingLogout]);

  // 回話卡的展開／收合。
  //
  // ⚠️ 展開接的是**新內容抵達**（`replyText` 變了），不是整段合成完。分段播放的
  // 延遲優化（伺服器只先合成第一句就送出）就是為了讓長輩不用等 5–8 秒，卡片若等
  // 整段會把這個優化吃掉。
  // ⚠️ 用「render 期間調整 state」而不是 `useEffect` + `setState`：後者會多跑一次
  // commit（eslint 的 `react-hooks/set-state-in-effect` 擋的就是它），而且畫面會先
  // 閃一格舊值。這是 React 官方對「prop 變了要跟著調整 state」的建議寫法。
  const [collapsed, setCollapsed] = useState(false);
  const [previous, setPrevious] = useState({ reply: talk.replyText, avatar: talk.avatar });

  if (previous.reply !== talk.replyText || previous.avatar !== talk.avatar) {
    const hasNewContent = previous.reply !== talk.replyText;
    const finishedSpeaking = previous.avatar === "speaking" && talk.avatar === "idle";
    setPrevious({ reply: talk.replyText, avatar: talk.avatar });
    if (hasNewContent) {
      // 新內容一到就展開。同一次變更裡「有新內容」永遠贏過「說完了」——不然
      // 下一輪的第一段抵達時會被上一輪的收合蓋掉，長輩看不到剛回的話。
      setCollapsed(false);
    } else if (finishedSpeaking) {
      // 說完了（speaking → idle）才收合成單行摘要，主鍵同時長回 132。
      setCollapsed(true);
    }
  }

  // 一輪結束就寫進當日紀錄（W4）。
  //
  // ⚠️ 放在畫面層而不是 `useTalk`：與 App 一致（App 也寫在 talk.tsx），而且 useTalk
  // 的播放佇列有補播與插嘴的競態，把寫入塞進去要動到那一段。`collapsed` 翻成 true
  // 的那一刻就是「答案播完了」，正是要記的時機。
  //
  // ⚠️ `said` 或 `reply` 任一為空就不寫：舊版後端不送 `transcript`，寧可少一則紀錄，
  // 也不要讓長輩看到一句他沒講過的話。
  const loggedReplyRef = useRef<string | null>(null);
  useEffect(() => {
    if (!collapsed) return;
    const said = talk.transcript.trim();
    const reply = talk.replyText.trim();
    if (!said || !reply) return;
    // 同一輪只寫一次：`collapsed` 期間任何重繪都會再跑一次這個 effect。
    if (loggedReplyRef.current === reply) return;
    loggedReplyRef.current = reply;
    void appendTurn({ at: Date.now(), said, reply });
  }, [collapsed, talk.transcript, talk.replyText]);

  const showCollapsed = collapsed && talk.replyText.trim().length > 0;

  return (
    <div className="elder-gradient relative h-full overflow-hidden">
      {/* ── 頁首（z40） ─────────────────────────────────────────────── */}
      <div
        style={{ top: HEADER_TOP }}
        className="absolute inset-x-[var(--size-elder-page-padding)] z-40 flex items-center gap-2.5"
      >
        <button
          type="button"
          onClick={props.onOpenHistory}
          aria-label={strings.elderHistory.entryButton}
          className="flex size-[var(--size-elder-round-button)] shrink-0 items-center justify-center rounded-full border border-line bg-surface text-3xl text-primary shadow-[var(--elevation-row)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span aria-hidden>🕘</span>
        </button>

        <button
          type="button"
          aria-label={
            props.unread > 0
              ? strings.elderNotifications.bellWithUnread(props.unread)
              : strings.elderNotifications.bell
          }
          onClick={props.onOpenNotifications}
          className="relative flex size-[var(--size-elder-round-button)] items-center justify-center rounded-full border border-line bg-surface text-2xl shadow-[var(--elevation-row)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span aria-hidden>🔔</span>
          {props.unread > 0 ? (
            // 紅點只是給看得見的人的捷徑；真正的數字在上面的 aria-label 裡。
            // 字級仍受長輩端 22px 下限約束——14px 的數字他看不清，那條捷徑就不存在。
            <span
              aria-hidden
              className="absolute -right-1 -top-1 flex min-w-8 items-center justify-center rounded-full bg-danger-badge px-1 text-elder-min font-bold leading-none text-white"
            >
              {props.unread > 9 ? "9+" : props.unread}
            </span>
          ) : null}
        </button>

        <span className="flex-1" />

        <button
          type="button"
          onClick={() => setIsConfirmingLogout(true)}
          disabled={isConfirmingLogout}
          // ⚠️ 長輩端可點擊目標一律 ≥56px、字級 ≥22px，次要按鈕也不例外。
          className="min-h-14 rounded-pill px-4 text-elder-min text-ink-soft disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {strings.talk.logout}
        </button>
      </div>

      {/* ── 角色舞台（z10，固定，永不縮放或位移） ────────────────────── */}
      <div
        style={{ top: STAGE_TOP }}
        className="absolute left-1/2 z-10 -translate-x-1/2"
      >
        {/* speechCue＝阿白正在講的那一段（字＋時長），renderer 據此逐字對嘴。
            ⚠️ 不傳 `emotion`：後端目前不回傳回應情緒，renderer 會自己從這段話
            判讀（見 `BearStage` 的 emotion prop 說明）。 */}
        <BearStage state={talk.avatar} speechCue={talk.speechCue} />
      </div>

      {/* ── 內容層（z20，貼底往上長） ────────────────────────────────── */}
      <div
        style={{ bottom: isSpeaking ? CONTENT_BOTTOM_SPEAKING : CONTENT_BOTTOM }}
        className="absolute inset-x-[var(--size-elder-page-padding)] z-20 flex flex-col gap-2 transition-[bottom] duration-[var(--motion-layout)] ease-out"
      >
        {showCollapsed ? (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            aria-label={strings.talk.collapsedPrefix + talk.replyText}
            data-testid="reply-collapsed"
            className="flex min-h-[70px] w-full items-center rounded-card border border-line bg-surface px-[18px] text-left text-elder-min font-bold text-ink shadow-[var(--elevation-sheet)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span className="truncate">{collapsedSummary(talk.replyText)}</span>
          </button>
        ) : (
          <div
            data-testid="reply-card"
            className="w-full rounded-card border border-line bg-surface p-[18px] shadow-[var(--elevation-sheet)]"
          >
            {/* 回話內文是這個畫面唯一的產出，讀螢幕的人不會自己去掃畫面找它；
                polite 語意不會打斷目前的朗讀。
                max-height＋overflow：字級放大時只有這一塊捲，見檔頭說明。 */}
            <p
              role="status"
              className="max-h-[330px] overflow-y-auto text-[24px] font-bold leading-[35px] text-ink"
            >
              {talk.replyText}
            </p>
          </div>
        )}

        {/* 狀態帶：顏色＋圖示＋文字三重編碼（規則 6），拿掉顏色仍讀得懂。 */}
        <div
          data-testid="talk-status-band"
          style={{
            backgroundColor: `var(--talk-${talk.avatar}-pill)`,
            color: `var(--talk-${talk.avatar}-ink)`,
          }}
          className="flex items-center gap-2.5 rounded-pill px-4 py-3 transition-colors duration-[var(--motion-state)]"
        >
          <TalkStatusIcon state={talk.avatar} size={28} className="shrink-0" />
          <span className="text-elder-min font-extrabold">{strings.talk.status[talk.avatar]}</span>
          <span className="text-elder-min opacity-80">{strings.talk.statusSub[talk.avatar]}</span>
        </div>
      </div>

      {/* ── 主鍵（z30，bottom 40） ───────────────────────────────────── */}
      <div
        style={{ bottom: MIC_BOTTOM }}
        className={`absolute inset-x-0 z-30 flex items-center justify-center gap-3 ${
          isSpeaking ? "flex-row" : "flex-col"
        }`}
      >
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
          data-testid="talk-mic"
          // touch-none：不讓瀏覽器把「按住」判成捲動而把手勢搶走。
          // select-none：iOS 長按會跳出選字放大鏡，蓋住半個畫面。
          style={{
            width: isSpeaking ? MIC_SIZE_SMALL : MIC_SIZE,
            height: isSpeaking ? MIC_SIZE_SMALL : MIC_SIZE,
            backgroundColor: isSpeaking ? "var(--talk-idle-pill)" : "var(--color-action)",
            color: isSpeaking ? "var(--talk-idle-ink)" : "var(--color-ink)",
          }}
          className={`flex shrink-0 touch-none select-none items-center justify-center rounded-full shadow-[var(--elevation-action)] transition-[width,height,background-color,color] duration-[var(--motion-layout)] ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
            disabled ? "opacity-50" : ""
          }`}
        >
          <MicIcon size={isSpeaking ? 34 : 60} />
        </button>
        <span
          className={`text-elder-min font-bold text-ink ${isSpeaking ? "max-w-[190px]" : ""}`}
        >
          {actionLabel(talk.avatar)}
        </span>
      </div>

      {/* ── 登出二次確認（z50，疊在最上層） ──────────────────────────── */}
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
          aria-label={strings.talk.logoutConfirmTitle}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setIsConfirmingLogout(false);
            }
          }}
          className="absolute inset-x-[var(--size-elder-page-padding)] top-1/2 z-50 flex -translate-y-1/2 flex-col gap-3 rounded-card border-2 border-danger bg-surface p-4 shadow-[var(--elevation-overlay)]"
        >
          <p className="text-elder-min font-bold leading-relaxed text-ink">
            {strings.talk.logoutConfirmBody}
          </p>
          <div className="flex gap-2">
            <Button
              label={strings.talk.confirmLogoutButton}
              size="big"
              variant="danger"
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
    </div>
  );
}
