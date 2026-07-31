/**
 * 相機掃碼。
 *
 * jsdom 沒有相機也沒有 WebAssembly 執行環境，所以測的是**契約**：權限被拒時
 * 要回報、掃到同一個碼只回報一次、停止後不再回報、相機軌道在每一條路徑都會
 * 釋放。真正的畫面擷取與解碼藏在 `scanFrame` 這個注入點後面（見
 * `qrScanner.ts`），本檔餵假的解碼結果進去，不碰真正的解碼。真正的解碼由人工
 * 在三家瀏覽器上驗收。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { createQrScanner } from "./qrScanner";

afterEach(() => vi.unstubAllGlobals());

function fakeVideo(): HTMLVideoElement {
  const video = document.createElement("video");
  Object.defineProperty(video, "videoWidth", { value: 640 });
  Object.defineProperty(video, "videoHeight", { value: 480 });
  video.play = vi.fn().mockResolvedValue(undefined);
  return video;
}

/** 手動控制的注入點：不用 `setIntervalFn`／`clearIntervalFn` 真的等 timer，測試手動觸發。 */
function captureTick(): {
  setIntervalFn: (fn: () => void) => number;
  clearIntervalFn: (handle: unknown) => void;
  waitForTick: () => Promise<() => void>;
} {
  let tick: (() => void) | null = null;
  return {
    setIntervalFn: (fn) => {
      tick = fn;
      return 0;
    },
    clearIntervalFn: () => {},
    waitForTick: async () => {
      await vi.waitFor(() => expect(tick).not.toBeNull());
      return tick!;
    },
  };
}

describe("createQrScanner", () => {
  it("使用者拒絕相機時回報 denied，不擲例外", async () => {
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(new Error("NotAllowedError")) },
    });
    const onError = vi.fn();
    createQrScanner({ video: fakeVideo(), onCode: vi.fn(), onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith("denied"));
  });

  it("瀏覽器沒有相機 API 時回報 unsupported", async () => {
    vi.stubGlobal("navigator", {});
    const onError = vi.fn();
    createQrScanner({ video: fakeVideo(), onCode: vi.fn(), onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith("unsupported"));
  });

  it("停止時關掉相機軌道", async () => {
    const stop = vi.fn();
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    const scanner = createQrScanner({ video: fakeVideo(), onCode: vi.fn() });
    await vi.waitFor(() => expect(stop).not.toHaveBeenCalled());
    scanner.stop();
    await vi.waitFor(() => expect(stop).toHaveBeenCalled());
  });

  it("相機權限視窗還沒回來就呼叫 stop()，權限批准後仍要關閉軌道", async () => {
    // 找到的問題（brief 未涵蓋）：使用者秒退（切到別頁、按返回），這時
    // getUserMedia 的權限請求可能還飛在半空中。若沒有這條路徑，等權限真的
    // 批准下來，軌道會沒有任何人記得關掉——跟 recorder.ts 的重入洩漏是同一種
    // 錯誤形狀（見 Task 4）。用手動控制的 Promise，不能用 mockResolvedValue
    // ——同一個 microtask 解出就看不到「停止發生在批准之前」這個中間狀態。
    const stop = vi.fn();
    let resolveGetUserMedia: ((stream: unknown) => void) | null = null;
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockReturnValue(
          new Promise((resolve) => {
            resolveGetUserMedia = resolve;
          }),
        ),
      },
    });
    const scanner = createQrScanner({ video: fakeVideo(), onCode: vi.fn() });
    scanner.stop(); // 權限視窗都還沒回來，使用者已經離開畫面
    resolveGetUserMedia!({ getTracks: () => [{ stop }] });
    await vi.waitFor(() => expect(stop).toHaveBeenCalled());
  });

  it("掃到碼只回報一次，不會因為連續幾幀都解出同一個碼而把呼叫端打爆", async () => {
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
      },
    });
    const onCode = vi.fn();
    const { setIntervalFn, clearIntervalFn, waitForTick } = captureTick();
    createQrScanner(
      { video: fakeVideo(), onCode },
      { scanFrame: vi.fn().mockResolvedValue("kinsun://bind/abc123"), setIntervalFn, clearIntervalFn },
    );
    const tick = await waitForTick();
    tick();
    await vi.waitFor(() => expect(onCode).toHaveBeenCalledTimes(1));
    tick(); // 下一幀又解出同一個碼
    tick(); // 再下一幀還是同一個碼
    await Promise.resolve();
    await Promise.resolve();
    expect(onCode).toHaveBeenCalledTimes(1);
    expect(onCode).toHaveBeenCalledWith("kinsun://bind/abc123");
  });

  it("這一幀沒有解出任何東西時不回報，也不當機", async () => {
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
      },
    });
    const onCode = vi.fn();
    const { setIntervalFn, clearIntervalFn, waitForTick } = captureTick();
    createQrScanner(
      { video: fakeVideo(), onCode },
      { scanFrame: vi.fn().mockResolvedValue(undefined), setIntervalFn, clearIntervalFn },
    );
    const tick = await waitForTick();
    tick();
    await Promise.resolve();
    await Promise.resolve();
    expect(onCode).not.toHaveBeenCalled();
  });

  it("解碼還在飛行中被 stop()，回來後不再回報已經離開畫面的呼叫端", async () => {
    // 審查發現的問題：brief 原始版本解碼（`await scanFrame`／原版 `readBarcodes`）
    // 回來後只重新檢查 `!reported`，沒有重新檢查 `stopped`——使用者按下停止鍵、
    // 相機軌道也關了，但飛行中的解碼若這時才解出東西，`onCode` 仍會被呼叫，
    // 通知一個已經離開這個畫面的呼叫端。用手動控制的 Promise 製造「解碼進行中
    // 被打斷」這個中間狀態，`mockResolvedValue` 做不到。
    const stop = vi.fn();
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    let resolveScan: ((text: string | undefined) => void) | null = null;
    const scanPromise = new Promise<string | undefined>((resolve) => {
      resolveScan = resolve;
    });
    const onCode = vi.fn();
    const { setIntervalFn, clearIntervalFn, waitForTick } = captureTick();
    const scanner = createQrScanner(
      { video: fakeVideo(), onCode },
      { scanFrame: vi.fn().mockReturnValue(scanPromise), setIntervalFn, clearIntervalFn },
    );
    const tick = await waitForTick();
    tick(); // 觸發一次解碼，尚未解出
    scanner.stop();
    expect(stop).toHaveBeenCalled(); // 停止當下軌道立刻釋放，不等解碼回來
    resolveScan!("kinsun://bind/abc123"); // 解碼終於回來，帶著一個有效的碼
    await scanPromise;
    await Promise.resolve(); // 讓 scanOnce() 內 await 之後的程式碼執行完
    expect(onCode).not.toHaveBeenCalled();
  });
});
