/**
 * 阿白的角色舞台。
 *
 * 取代原本的 emoji `Avatar`：角色改用 `shared/otto-pet-core` 的 SVG＋即時 rig，
 * 與 App 載入**同一份** `renderer.html`（`public/otto/`，由
 * `shared/otto-pet-core/build-renderer.mjs` 產出兩份）。情緒黑名單與注音 viseme
 * 對嘴因此只有一份實作——那是接手指示第 10 條、CRITICAL 等級的約束。
 *
 * ⚠️ 舞台 209 × 300 是核准值，**永不縮放或位移**（規則 3）。它的絕對定位（固定
 * top 140）由 `TalkScreen` 負責——本元件只保證自己的尺寸不變，需要空間時讓位的是
 * 麥克風主鍵與回話卡，不是角色。
 *
 * ⚠️ **W3b 起舞台是純裝飾**（與 App 一致）：狀態改由狀態帶的**可見文字**說出來
 * （「阿白正在說話」＋「聽完再按一下就好」）。W3a 期間這裡掛過 `role="img"` 與
 * 逐狀態的 `aria-label`，那是因為當時還沒有狀態帶，拿掉會讓看不見的長輩失去唯一
 * 線索；狀態帶到位後那組 aria-label 就退場了——可見文字比 aria-label 好，看得見的
 * 人與聽的人拿到同一份資訊，也不會有「同一個狀態兩套說法」的漂移。
 *
 * ⚠️ **2026-08-16 起 `aria-hidden` 掛在兩個裝飾層上、不掛在外層容器**：待機時浮出來
 * 的可點道具（戳泡泡、餵他一條魚⋯）必須進得了輔助科技的樹，而被祖先 `aria-hidden`
 * 蓋住的按鈕在讀螢幕軟體眼中不存在。「純裝飾」的意思沒有變——沒有道具的時候舞台裡
 * 一個可及的東西都沒有，狀態仍然只由狀態帶說。⚠️ 道具**只在網頁版**（✅ 裁決
 * 2026-08-16）：App 端不畫這顆按鈕，renderer 照發事件但沒有人接。
 *
 * ⚠️ 沒有靜態暫用圖。App 那側 renderer 未就緒時退回 `akin-hero.png`，而那張是
 * 舊角色阿金（黃金獵犬），已列在驗收報告。網頁版不重複這個錯：未就緒時只留光暈，
 * iframe 讀的是同源的本機檔案，不會等很久。
 */

import { useEffect, useRef, useState } from "react";

import {
  createOttoGreetCommand,
  createOttoLookCommand,
  createOttoSyncCommand,
  createOttoTapCommand,
  parseOttoRendererEvent,
  type OttoIdleProp,
  type OttoSpeechCue,
} from "kinsun-shared/ottoBridge";
import { prefersReducedMotion } from "@/stage/reducedMotion";
import { strings } from "@/strings";

import { bearSpeechCue } from "./bearEmotion";
import type { AvatarState } from "./useTalk";

/** 產物與 App 同源同檔；`base` 由 Vite 注入（正式掛在 /demo/）。 */
const RENDERER_SRC = `${import.meta.env.BASE_URL}otto/renderer.html`;

export function BearStage(props: {
  state: AvatarState;
  speechCue?: OttoSpeechCue | null;
  /**
   * 回應情緒。⚠️ 後端目前不回傳這個欄位（全庫 `src/` 沒有 emotion 的概念），所以
   * 呼叫端一律不傳、此處恆為 `undefined`——與 App 端 `talk.tsx` 的 `replyEmotion`
   * 是同一個呈現層接點。那時 renderer 會用 `senseEmotion()` 從阿白**自己講的話**
   * 判讀情緒（`sentiment.js`，50 種），所以不傳並不等於沒有情緒。
   */
  emotion?: string | null;
}) {
  const { state } = props;
  const speechCue = bearSpeechCue(state, props.emotion, props.speechCue ?? null);
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const sequenceRef = useRef(0);
  /** 這一次掛載打過招呼了沒。⚠️ 不可以每次回到待機都揮手——那會變成句句話的結尾動作。 */
  const greetedRef = useRef(false);
  const [isReady, setIsReady] = useState(false);
  /**
   * 待機時浮出來的可點小道具（戳泡泡、餵他一條魚⋯），由 renderer 主動回報。
   *
   * ⚠️ **只有待機態顯示**：長輩正要說話或正在聽答案時，畫面上不可以多一個會動的
   * 東西跟麥克風鍵搶手指。renderer 那側待機被 `suspend()` 時本來就會送收起來，這裡
   * 不賭「狀態切換」與「訊息抵達」的先後。
   */
  const [idleProp, setIdleProp] = useState<OttoIdleProp | null>(null);

  useEffect(() => {
    function receive(event: MessageEvent) {
      // 只認自己那個 iframe 送來的訊息：頁面上任何腳本（含瀏覽器擴充）都能對
      // window 送 message，不驗來源的話會被別人的訊息騙進 ready。
      if (!frameRef.current || event.source !== frameRef.current.contentWindow) return;
      if (typeof event.data !== "string") return;
      const message = parseOttoRendererEvent(event.data);
      if (message?.type === "idle-prop") {
        setIdleProp(message.prop);
        return;
      }
      if (message?.type !== "ready") return;
      // ⚠️ 這裡**只開開關、不送指令**：補送由下面那條 effect 負責（`isReady` 在它
      // 的相依陣列裡，轉真時會以當下的狀態送出一則）。兩邊都送的話 renderer 會在
      // ready 的瞬間連收兩則同狀態指令——而重送 speaking 會讓 `TalkDriver.talk()`
      // 先 `stop()` 再從頭開始，阿白的嘴會把同一句重對一次。
      setIsReady(true);
    }
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, []);

  // ⚠️ `isReady` 也在相依陣列裡：renderer 起來之前的狀態變化只會累加序號、不送出，
  // ready 轉真時這條會以**當下**的狀態補送一則——renderer 剛起來時錯過的那幾個狀態
  // 因此不需要另外記，最後一個就是它現在該呈現的樣子。
  useEffect(() => {
    if (!isReady) return;
    sequenceRef.current += 1;
    const command = createOttoSyncCommand(sequenceRef.current, state, speechCue);
    frameRef.current?.contentWindow?.postMessage(JSON.stringify(command), "*");

    // ⚠️ 打招呼**排在狀態指令後面**（同一條 effect 內，不另開一條）：renderer 要先
    // 知道自己該是什麼樣子，再演這一段；反過來的話補送的狀態會把打招呼當場蓋掉。
    if (greetedRef.current) return;
    greetedRef.current = true;
    // 只在他真的在待機時打招呼——就緒的那一刻若長輩已經在講話或在等答案，揮手是打斷。
    // 減少動態效果時同樣不演（與視線追蹤同一個理由）。
    if (state !== "idle" || prefersReducedMotion()) return;
    frameRef.current?.contentWindow?.postMessage(
      JSON.stringify(createOttoGreetCommand()),
      "*",
    );
  }, [state, speechCue, isReady]);

  // 視線追蹤：阿白的眼睛與頭跟著指標轉。
  //
  // ⚠️ **監聽掛在 `window` 而不是 iframe 上**：iframe 是 `pointer-events: none` 且
  // 不給 `allow-same-origin`，它自己收不到、我們也伸不進去。座標在這一層換算完才
  // 送進去——renderer 沒有頁面座標系的概念（它只有自己那 908×1250 的 viewBox）。
  //
  // ⚠️ **滿量程用視窗的一半、不是舞台的一半**：以舞台為基準的話，指標離開舞台一個
  // 身位就飽和了，之後再怎麼移動阿白都不動；以視窗為基準，指標在畫面任何位置都對應
  // 到合理的角度，而「靠近阿白」與「在螢幕角落」看起來是不同的方向。
  useEffect(() => {
    // ⚠️ 尊重「減少動態效果」：前庭功能障礙的使用者會因為跟著自己動的畫面而暈眩。
    // renderer 那側讀同一個系統設定關掉動畫，這裡連訊息都不送。
    if (!isReady || prefersReducedMotion()) return;

    let pending: { x: number; y: number } | null = null;
    let frameId = 0;

    const send = (x: number | null, y: number | null) => {
      frameRef.current?.contentWindow?.postMessage(
        JSON.stringify(createOttoLookCommand(x, y)),
        "*",
      );
    };

    // ⚠️ 每一幀最多送一則：`pointermove` 的頻率遠高於畫面更新（高更新率的觸控螢幕
    // 一秒可以送兩三百則），每一則都 `postMessage`＋`JSON.stringify` 是純浪費，而
    // 阿白最多也只能一幀動一次。送出的永遠是**最後**那個位置，中途的已經過期。
    const flush = () => {
      frameId = 0;
      if (!pending) return;
      const { x, y } = pending;
      pending = null;
      send(x, y);
    };

    const onMove = (event: PointerEvent) => {
      const host = hostRef.current;
      if (!host) return;
      const halfWidth = window.innerWidth / 2;
      const halfHeight = window.innerHeight / 2;
      // 視窗尺寸為 0（分頁在背景、jsdom 未設值）時換算會變成 Infinity／NaN，
      // 而那會讓 renderer 的 transform 整組失效、阿白直接消失。
      if (halfWidth <= 0 || halfHeight <= 0) return;
      const rect = host.getBoundingClientRect();
      pending = {
        x: (event.clientX - (rect.left + rect.width / 2)) / halfWidth,
        y: (event.clientY - (rect.top + rect.height / 2)) / halfHeight,
      };
      if (frameId === 0) frameId = requestAnimationFrame(flush);
    };

    const recenter = () => {
      pending = null;
      if (frameId !== 0) {
        cancelAnimationFrame(frameId);
        frameId = 0;
      }
      send(null, null);
    };

    // ⚠️ **只有觸控在放開時回正**：滑鼠放開按鍵不代表人走了，視線該留在原處；
    // 手指離開玻璃就真的沒有指標了，不回正的話眼珠會一直斜著看最後那個位置。
    const onUp = (event: PointerEvent) => {
      if (event.pointerType === "touch") recenter();
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    // 滑鼠移出整個視窗（切到別的視窗、移到瀏覽器工具列）。
    document.addEventListener("mouseleave", recenter);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      document.removeEventListener("mouseleave", recenter);
      if (frameId !== 0) cancelAnimationFrame(frameId);
    };
  }, [isReady]);

  const visibleProp = state === "idle" ? idleProp : null;

  return (
    // ⚠️ **外層不再整塊 `aria-hidden`**（W3b 起它是的）：可點的道具必須進得了輔助
    // 科技的樹，被祖先 `aria-hidden` 蓋住的按鈕在讀螢幕軟體眼中不存在，鍵盤走到它
    // 時也讀不出任何東西。「舞台是純裝飾」這件事沒有變——光暈與 renderer 兩個裝飾層
    // 各自帶著自己的 `aria-hidden`，狀態仍然由狀態帶的可見文字說；唯一的例外就是
    // 這顆真的可以按的道具，而它有自己講得清楚的可及名稱。
    <div
      ref={hostRef}
      className="relative h-[var(--avatar-stage-h)] w-[var(--avatar-stage-w)] shrink-0"
      data-testid="bear-stage"
    >
      {/* CSS 有 radial-gradient，不必像 RN 那樣用大圓角色塊近似。 */}
      <div
        aria-hidden
        data-testid="bear-stage-glow"
        className="pointer-events-none absolute -inset-6 rounded-full blur-xl transition-[background] duration-[var(--motion-state)]"
        style={{ background: `var(--talk-${state}-glow)` }}
      />
      <iframe
        ref={frameRef}
        src={RENDERER_SRC}
        title={strings.talk.companionTitle}
        aria-hidden
        tabIndex={-1}
        // allow-scripts 之外一律不給：renderer 沒有網路、沒有表單、沒有導覽需求，
        // CSP 也已經是 default-src 'none'。不給 allow-same-origin 讓它是不透明來源，
        // 即使 renderer 出問題也碰不到頁面的 storage 與 cookie。
        sandbox="allow-scripts"
        scrolling="no"
        className={`pointer-events-none absolute inset-0 size-full border-0 bg-transparent transition-opacity duration-[var(--motion-state)] ${
          isReady ? "opacity-100" : "opacity-0"
        }`}
      />
      {visibleProp ? (
        <button
          type="button"
          // ⚠️ 每個道具一顆新的按鈕（key 帶道具名）：換道具時若沿用同一顆，React 會
          // 保留 DOM 節點，正在跑的浮現動畫會從上一個道具的進度接下去。
          key={visibleProp.key}
          data-testid="bear-idle-prop"
          onClick={() => {
            frameRef.current?.contentWindow?.postMessage(
              JSON.stringify(createOttoTapCommand()),
              "*",
            );
            // 樂觀收起來：renderer 那側一次待機也只認第一下（`Idle.tap()` 的 `hit`
            // 旗標），留著只會讓長輩再按一次卻沒有反應。
            setIdleProp(null);
          }}
          // emoji 對讀螢幕軟體幾乎沒有資訊量，可及名稱要自己講清楚「這是什麼、按了
          // 會怎樣」。`title` 讓滑鼠使用者也讀得到同一句。
          aria-label={`${visibleProp.zh}：${visibleProp.label}`}
          title={`${visibleProp.zh}：${visibleProp.label}`}
          style={{ left: `${visibleProp.x}%`, top: `${visibleProp.y}%` }}
          // 56px 是長輩端可點目標的下限；`-translate-*` 讓 renderer 給的座標落在
          // 按鈕**中心**而不是左上角。
          className="absolute size-14 -translate-x-1/2 -translate-y-1/2 rounded-full bg-surface/80 text-[30px] leading-none shadow-[var(--elevation-sheet)] backdrop-blur-sm transition-transform duration-[var(--motion-state)] hover:scale-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span aria-hidden>{visibleProp.icon}</span>
        </button>
      ) : null}
    </div>
  );
}
