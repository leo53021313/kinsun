/**
 * 開場頁退進一圈光裡：從使用者按下的按鈕中心綻放暖黃光暈，開場頁同時淡出並
 * 微幅放大，光散去就是後方已經掛好的雙欄舞台（spec 2026-08-13）。
 *
 * ⚠️ 這裡原本是「撕裂展開」（沿鋸齒裂痕切兩半滑開）。換掉的理由是調性、不是技術：
 * 「撕開」帶破壞感，與陪伴長輩的產品衝突。動作的隱喻改成「你伸手一按，畫面為你
 * 亮起來」——起點是使用者的手指，而不是一道裂痕。
 *
 * ⚠️ 舞台由呼叫端在動畫**期間**就掛載（見 App.tsx）：等動畫播完才開始請求，
 * 使用者會平白多等 700 毫秒，而那正是他最沒有耐心的時刻。
 *
 * ⚠️ 尊重 prefers-reduced-motion（W-11）：純視覺享受不該讓對動態敏感的人不舒服。
 * 判斷式抽到 `stage/reducedMotion.ts`，與 `notify/NotificationBanner.tsx` 共用同一份。
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { prefersReducedMotion } from "./reducedMotion";

export const BLOOM_DURATION_MS = 700;
export const REDUCED_MOTION_MS = 200;

/** 光暈圓心，視窗座標（overlay 是 fixed，兩者同一個座標系）。 */
export type BloomOrigin = { x: number; y: number };

/**
 * 光暈的放大與淡出**用兩條不同的曲線**，不可共用一條。
 *
 * ⚠️ 這是實測改出來的（2026-08-13，Playwright 逐格量測）：原本兩者共用
 * `cubic-bezier(0.22, 1, 0.36, 1)`（easeOutQuint），量到的結果是光暈在轉場開始後
 * **240 毫秒就淡到 opacity 0.10**、等於看不見了，而開場頁的淡出要跑滿 700 毫秒。
 * 畫面上讀起來是「閃一下，然後一段無關的淡出」——正是設計要避免的「爆開」。
 *
 * - 放大用 easeOutCubic：夠快但不暴衝，整段時間都還在長大。
 * - 淡出用前段平緩、後段才收的曲線：光要撐到轉場中後段才散，才叫「綻放」。
 */
const GLOW_EXPAND_EASING = "cubic-bezier(0.33, 1, 0.68, 1)";
const GLOW_FADE_EASING = "cubic-bezier(0.4, 0, 1, 1)";

/**
 * 光暈淡出的延遲與長度。**不可讓它跑滿 `BLOOM_DURATION_MS`**。
 *
 * ⚠️ 轉場的 CSS 從畫面上真的開始動，比 `onDone` 的計時器起跑晚了約 100 毫秒
 * （計時器在 effect 就起跑，CSS 要等 rAF ＋ 再一次 render／commit ／首次繪製）。
 * 淡出若也用 700 毫秒，`onDone` 觸發、overlay 被拔掉的當下光暈還有約三成不透明度
 * ——畫面上金光會「啪」一聲被切掉（Playwright 逐格量測到 0.33，2026-08-13）。
 * 讓它提早收乾淨，這個落差就吃得掉，慢的機器上也還有餘裕。
 */
const GLOW_FADE_DELAY_MS = 150;
const GLOW_FADE_MS = 420;

/**
 * 光暈底色。用主題 token 而非寫死色碼，品牌色改了它會跟著改。
 * 邊緣柔化到透明，讀起來才是「光」而不是「一塊黃色圓形」。
 */
const BLOOM_GRADIENT = [
  "radial-gradient(circle,",
  "var(--color-action) 0%,",
  "color-mix(in srgb, var(--color-action) 55%, transparent) 45%,",
  "transparent 70%)",
].join(" ");

export function BloomTransition(props: {
  active: boolean;
  onDone: () => void;
  origin?: BloomOrigin;
  children: ReactNode;
}) {
  const { active, onDone, origin, children } = props;
  const [reduced] = useState(prefersReducedMotion);
  // 掛上之後才加位移，否則會直接出現在終點、看不到過程。
  const [moved, setMoved] = useState(false);

  // ⚠️ onDone 存進 ref、不進相依陣列：舞台在動畫**期間**就掛載並發請求（見上方
  // 說明），那正是父層最容易重新渲染的時刻。onDone 若留在相依陣列，父層一重繪就
  // 會清掉計時器、重排一顆新的——「播完通知呼叫端」這個契約會被延後，極端情況下
  // 永遠不觸發。用獨立的 effect 同步而非 render 期間直接賦值：後者會被
  // react-hooks 的 refs 規則抓到。
  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (!active) {
      return;
    }
    const raf = requestAnimationFrame(() => setMoved(true));
    const timer = setTimeout(
      () => onDoneRef.current(),
      reduced ? REDUCED_MOTION_MS : BLOOM_DURATION_MS,
    );
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
    };
  }, [active, reduced]);

  if (!active) {
    return <>{children}</>;
  }

  if (reduced) {
    return (
      <div
        aria-hidden
        className="transition-opacity ease-out"
        style={{ opacity: moved ? 0 : 1, transitionDuration: `${REDUCED_MOTION_MS}ms` }}
      >
        {children}
      </div>
    );
  }

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-50 overflow-hidden">
      {/* 開場頁副本：淡出並微幅**放大**。縮小讀起來是「被推走」，放大才是
          「退進光裡」；幅度只有 4%，再大就變成 zoom 特效、蓋過光暈本身。 */}
      <div
        data-testid="bloom-page"
        className="absolute inset-0 transition-[opacity,transform] ease-out"
        style={{
          opacity: moved ? 0 : 1,
          transform: moved ? "scale(1.04)" : "scale(1)",
          transitionDuration: `${BLOOM_DURATION_MS}ms`,
        }}
      >
        {children}
      </div>
      {/* 光暈：40vmax 見方的圓，用 vmax 而非固定 px，直式與橫式螢幕都蓋得滿；
          放大到 4 倍必定覆蓋整個視窗。 */}
      <div
        data-testid="bloom-glow"
        className="absolute size-[40vmax] rounded-full"
        style={{
          left: origin ? `${origin.x}px` : "50%",
          top: origin ? `${origin.y}px` : "50%",
          background: BLOOM_GRADIENT,
          opacity: moved ? 0 : 0.9,
          transform: `translate(-50%, -50%) scale(${moved ? 4 : 0.2})`,
          // 兩個屬性各自的延遲、長度與曲線，順序與 transitionProperty 一一對應
          // （見上方說明：放大跑滿全程，淡出先撐住再提早收乾淨）。
          transitionProperty: "opacity, transform",
          transitionDelay: `${GLOW_FADE_DELAY_MS}ms, 0ms`,
          transitionDuration: `${GLOW_FADE_MS}ms, ${BLOOM_DURATION_MS}ms`,
          transitionTimingFunction: `${GLOW_FADE_EASING}, ${GLOW_EXPAND_EASING}`,
        }}
      />
    </div>
  );
}
