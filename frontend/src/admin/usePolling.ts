import { useEffect, useRef } from "react";

/** 每 intervalMs 執行一次 callback；分頁不可見時暫停，回到前景立即補跑一次。 */
export function usePolling(callback: () => void | Promise<void>, intervalMs: number): void {
  const saved = useRef(callback);
  // ref 的更新要落在 render 之後：render 期間改 ref 會讓 React 讀到不一致的值
  // （並發渲染下 render 可能被丟棄重跑）。無相依陣列＝每次 render 後都更新，
  // 正是此處要的語意——saved.current 永遠是最新的 callback，而下方輪詢的
  // useEffect 相依 [intervalMs]、不因 callback 變動而重啟計時器，這正是本 hook
  // 用 ref 的初衷，修正後仍然成立。
  useEffect(() => {
    saved.current = callback;
  });

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
