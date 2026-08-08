/**
 * 阿白的角色舞台（W3a）。
 *
 * 取代原本的 emoji `Avatar`：角色改用 `shared/otto-pet-core` 的 SVG＋即時 rig，
 * 與 App 載入**同一份** `renderer.html`（`public/otto/`，由
 * `shared/otto-pet-core/build-renderer.mjs` 產出兩份）。情緒黑名單與注音 viseme
 * 對嘴因此只有一份實作——那是接手指示第 10 條、CRITICAL 等級的約束。
 *
 * ⚠️ **W3a 只換角色，不動版面。** 舞台尺寸已是核准的 209 × 300，但它現在仍待在
 * `TalkScreen` 原本的 flex 直欄裡；改成「固定 top 140、四層絕對定位、一屏不捲」
 * 是 W3b 的事。分兩步是為了出錯時分得出來是渲染還是版面。
 *
 * ⚠️ **`role="img"` 與 `aria-label` 必須留著。** App 那側的舞台是純裝飾
 * （`accessibilityElementsHidden`），因為狀態由狀態帶的文字說出來；網頁版的狀態帶
 * 要到 W3b 才有，這裡先拿掉的話，看不見的長輩會完全失去「阿白現在在聽還是在想」
 * 這個唯一線索。
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

import type { AvatarState } from "./useTalk";

/** 產物與 App 同源同檔；`base` 由 Vite 注入（正式掛在 /demo/）。 */
const RENDERER_SRC = `${import.meta.env.BASE_URL}otto/renderer.html`;

export function BearStage(props: { state: AvatarState; speechCue?: OttoSpeechCue | null }) {
  const { state, speechCue = null } = props;
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
      role="img"
      aria-label={strings.talk.avatar[state]}
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
        title={strings.talk.avatar[state]}
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
