import { useEffect, useRef } from "react";

/** 每 intervalMs 執行一次 callback；分頁不可見時暫停，回到前景立即補跑一次。 */
export function usePolling(callback: () => void | Promise<void>, intervalMs: number): void {
  const saved = useRef(callback);
  saved.current = callback;

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;

    const tick = () => void saved.current();

    const start = () => {
      if (timer === null) {
        tick();
        timer = setInterval(tick, intervalMs);
      }
    };

    const stop = () => {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    };

    const onVisibility = () => (document.hidden ? stop() : start());

    document.addEventListener("visibilitychange", onVisibility);
    start();
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
    };
  }, [intervalMs]);
}
