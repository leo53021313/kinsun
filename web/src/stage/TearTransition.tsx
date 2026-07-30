/**
 * 開場頁沿一道不規則裂痕撕成左右兩半、各自往外滑開（spec §5.2）。
 *
 * 做法：把同一份內容渲染兩次，各用一個 clip-path 只留下裂痕的一側，然後兩側
 * 各自平移並微幅傾斜。這比用一張遮罩圖便宜（零額外請求）、也比 canvas 簡單。
 *
 * ⚠️ 舞台由呼叫端在動畫**期間**就掛載（見 App.tsx）：等動畫播完才開始請求，
 * 使用者會平白多等 700 毫秒，而那正是他最沒有耐心的時刻。
 *
 * ⚠️ 尊重 prefers-reduced-motion（W-11）：純視覺享受不該讓對動態敏感的人不舒服。
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

export const TEAR_DURATION_MS = 700;
export const REDUCED_MOTION_MS = 200;

/**
 * 裂痕的形狀：由上到下的一串轉折點（百分比）。左半留裂痕左側、右半留右側。
 * 手調的鋸齒——完全的直線看起來像滑門而不是撕開。
 */
const TEAR_X = [50, 46, 53, 44, 55, 47, 52, 45, 50];

function clipPath(side: "left" | "right"): string {
  const steps = TEAR_X.length - 1;
  const points = TEAR_X.map((x, i) => `${x}% ${(i / steps) * 100}%`);
  return side === "left"
    ? `polygon(0% 0%, ${points.join(", ")}, 0% 100%)`
    : `polygon(100% 0%, ${points.join(", ")}, 100% 100%)`;
}

function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function TearTransition(props: {
  active: boolean;
  onDone: () => void;
  children: ReactNode;
}) {
  const { active, onDone, children } = props;
  const [reduced] = useState(prefersReducedMotion);
  // 掛上之後才加位移，否則兩半會直接出現在終點、看不到過程。
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
      reduced ? REDUCED_MOTION_MS : TEAR_DURATION_MS,
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

  const half = (side: "left" | "right") => ({
    clipPath: clipPath(side),
    transform: moved
      ? `translateX(${side === "left" ? "-" : ""}60%) rotate(${side === "left" ? "-" : ""}3deg)`
      : "translateX(0) rotate(0deg)",
    transitionDuration: `${TEAR_DURATION_MS}ms`,
  });

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-50 overflow-hidden">
      {(["left", "right"] as const).map((side) => (
        <div
          key={side}
          data-testid={`tear-${side}`}
          className="absolute inset-0 transition-transform ease-[cubic-bezier(0.7,0,0.3,1)]"
          style={half(side)}
        >
          {children}
        </div>
      ))}
    </div>
  );
}
