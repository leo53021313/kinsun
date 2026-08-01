/**
 * 手機外框「內部」的畫面堆疊。
 *
 * ⚠️ 刻意不用 react-router：兩欄同時存在、各有各的畫面深度，讓它們去搶同一條
 * 瀏覽器網址只會互相覆蓋——右欄進到排程頁，左欄的網址也跟著變。
 */

import { useCallback, useMemo, useState } from "react";

export type ScreenStack<T> = {
  current: T;
  push: (next: T) => void;
  back: () => void;
  /** 清掉整個堆疊，從 next 重新開始（登入／登出後用）。 */
  reset: (next: T) => void;
  depth: number;
};

export function useScreenStack<T>(initial: T): ScreenStack<T> {
  const [stack, setStack] = useState<T[]>([initial]);

  const push = useCallback((next: T) => setStack((cur) => [...cur, next]), []);

  // ⚠️ 最底層不再往回退：退成空陣列的話 current 會是 undefined，整欄白畫面，
  // 而使用者連「返回」以外的按鈕都看不到。
  const back = useCallback(
    () => setStack((cur) => (cur.length > 1 ? cur.slice(0, -1) : cur)),
    [],
  );

  const reset = useCallback((next: T) => setStack([next]), []);

  return useMemo(
    () => ({ current: stack[stack.length - 1], push, back, reset, depth: stack.length }),
    [stack, push, back, reset],
  );
}
