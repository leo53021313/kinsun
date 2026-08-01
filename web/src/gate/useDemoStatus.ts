/**
 * 運營狀態的取得與輪詢。
 *
 * 為什麼要輪詢：這一頁最常見的情境是「有人剛下 kinsun.sh start，模型還在載入」。
 * 不自動重查的話，使用者得自己猜什麼時候該按重整——而他不知道要等多久。
 */

import { useEffect, useState } from "react";

import { getDemoStatus, type DemoStatus } from "@/api";

export type GateState = {
  status: DemoStatus | null;
  /** 連後端都打不到（伺服器沒開、網路不通）。與「後端回報停機」是兩件事。 */
  unreachable: boolean;
};

/** 這兩種整體狀態代表產品此刻可以操作。 */
const ENTERABLE = new Set(["available", "degraded"]);

export function canEnter(state: GateState): boolean {
  return state.status !== null && ENTERABLE.has(state.status.overall);
}

export function useDemoStatus(options: { intervalMs?: number } = {}): GateState {
  const intervalMs = options.intervalMs ?? 10_000;
  const [state, setState] = useState<GateState>({ status: null, unreachable: false });

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const status = await getDemoStatus();
        if (alive) {
          setState({ status, unreachable: false });
        }
      } catch {
        // 打不到後端與後端說自己停機，在畫面上是不同的兩句話——前者要去看伺服器
        // 有沒有開，後者要去看是哪個服務掛了。混成同一句會讓人查錯方向。
        if (alive) {
          setState({ status: null, unreachable: true });
        }
      }
    }
    void poll();
    const timer = setInterval(() => void poll(), intervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return state;
}
