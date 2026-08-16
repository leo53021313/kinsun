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
 * ⚠️ 沒有靜態暫用圖。App 那側 renderer 未就緒時退回 `akin-hero.png`，而那張是
 * 舊角色阿金（黃金獵犬），已列在驗收報告。網頁版不重複這個錯：未就緒時只留光暈，
 * iframe 讀的是同源的本機檔案，不會等很久。
 */

import { useEffect, useRef, useState } from "react";

import {
  createOttoSyncCommand,
  parseOttoRendererEvent,
  type OttoSpeechCue,
} from "kinsun-shared/ottoBridge";
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
  const sequenceRef = useRef(0);
  const latestCommandRef = useRef(createOttoSyncCommand(0, state, speechCue));
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    function receive(event: MessageEvent) {
      // 只認自己那個 iframe 送來的訊息：頁面上任何腳本（含瀏覽器擴充）都能對
      // window 送 message，不驗來源的話會被別人的訊息騙進 ready。
      if (!frameRef.current || event.source !== frameRef.current.contentWindow) return;
      if (typeof event.data !== "string") return;
      const message = parseOttoRendererEvent(event.data);
      if (message?.type !== "ready") return;
      setIsReady(true);
      // renderer 剛起來時可能已經錯過幾個狀態，補送最後一個。
      frameRef.current.contentWindow?.postMessage(
        JSON.stringify(latestCommandRef.current),
        "*",
      );
    }
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, []);

  useEffect(() => {
    sequenceRef.current += 1;
    const command = createOttoSyncCommand(sequenceRef.current, state, speechCue);
    latestCommandRef.current = command;
    if (isReady) {
      frameRef.current?.contentWindow?.postMessage(JSON.stringify(command), "*");
    }
  }, [state, speechCue, isReady]);

  return (
    <div
      aria-hidden
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
    </div>
  );
}
