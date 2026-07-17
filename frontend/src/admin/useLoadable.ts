/**
 * 把 admin 七頁重複的「載入 → 成功顯示資料／失敗顯示錯誤」模式收成一處。
 *
 * 這七頁原本各自手寫 useState 資料 ＋ useState 錯誤 ＋ useCallback 載入 ＋
 * useEffect(load, [load])，改一次載入行為要改七處（PR #56 就一次修了七遍）。
 */

import { useCallback, useEffect, useRef, useState } from "react";

export function useLoadable<T, E = true>(
  /**
   * 取資料。**必須是穩定參考**（以 useCallback 包過），否則每次 render 都會重載。
   * 回傳 null ＝ 條件未滿足（如 elderId 尚未從路由解析出來），這輪不載入。
   */
  fetcher: () => Promise<T> | null,
  /** 把例外譯成錯誤值。預設回 true。**不需要**穩定參考（見下方 mapErrorRef）。 */
  mapError?: (exc: unknown) => E,
): { data: T | null; error: E | null; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<E | null>(null);

  // mapError 以 ref 保存，故呼叫端不必 useCallback 包它：它是每次 render 都可能
  // 是新參考的回呼，若列入下方 reload 的相依，載入會無限重跑。ref 的更新落在
  // render 之後（render 期間改 ref 會讓並發渲染讀到不一致的值）。
  // 同款模式見 usePolling.ts。
  const mapErrorRef = useRef(mapError);
  useEffect(() => {
    mapErrorRef.current = mapError;
  });

  const reload = useCallback(() => {
    const pending = fetcher();
    if (pending === null) return;
    // setState 一律在非同步回呼中：寫在函式開頭會讓下方 useEffect 觸發連鎖重繪
    // （react-hooks/set-state-in-effect，PR #56 為此修了七頁）。
    // 錯誤也刻意留到成功才清——那是 PR #56 核定的語意：不會閃一下「載入中」
    // 再跳回錯誤。
    pending.then(
      (value) => {
        setData(value);
        setError(null);
      },
      (exc: unknown) => {
        const map = mapErrorRef.current ?? (() => true as unknown as E);
        setError(map(exc));
      },
    );
  }, [fetcher]);

  useEffect(reload, [reload]);

  return { data, error, reload };
}
