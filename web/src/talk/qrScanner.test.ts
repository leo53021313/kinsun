/**
 * 相機掃碼。
 *
 * jsdom 沒有相機也沒有 WebAssembly 執行環境，所以測的是**契約**：權限被拒時
 * 要依成因分類回報、掃到同一個碼只回報一次、停止後不再回報、逐幀節流不會
 * 疊加解碼、相機軌道在每一條路徑都會釋放。真正的畫面擷取與解碼藏在
 * `scanFrame` 這個注入點後面（見 `qrScanner.ts`），本檔餵假的解碼結果進去，
 * 不碰真正的解碼。真正的解碼由人工在三家瀏覽器上驗收。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { createQrScanner } from "./qrScanner";

afterEach(() => vi.unstubAllGlobals());

function fakeVideo(options: { videoWidth?: number } = {}): HTMLVideoElement {
  const video = document.createElement("video");
  Object.defineProperty(video, "videoWidth", { value: options.videoWidth ?? 640 });
  Object.defineProperty(video, "videoHeight", { value: 480 });
  video.play = vi.fn().mockResolvedValue(undefined);
  return video;
}

/**
 * 手動控制的注入點：不用真的等 timer，測試手動觸發。`setIntervalFn`／
 * `setTimeoutFn` 簽章相同（`(fn, ms) => handle`），共用同一支工廠。
 */
function captureScheduler(): {
  schedule: (fn: () => void) => number;
  cancel: (handle: unknown) => void;
  waitForScheduled: () => Promise<() => void>;
} {
  let captured: (() => void) | null = null;
  return {
    schedule: (fn) => {
      captured = fn;
      return 0;
    },
    cancel: () => {},
    waitForScheduled: async () => {
      await vi.waitFor(() => expect(captured).not.toBeNull());
      return captured!;
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
    // 審查 Minor 2：原本第一段 `waitFor` 斷言「stop 還沒被呼叫」在第一次
    // 檢查就通過，沒有真的等到「串流已開始」——拿掉下面 stop() 裡的軌道釋放
    // 那一行，這條測試仍可能因為 tick 順序恰好而全綠。改成等
    // `video.srcObject` 真的被賦值（jsdom 預設是 `undefined`，賦值後才變成
    // 真正的串流物件），確保 `scanner.stop()` 呼叫的當下已經在「已串流」
    // 這個確定的狀態，而不是碰運氣。
    const stop = vi.fn();
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    const video = fakeVideo();
    const scanner = createQrScanner({ video, onCode: vi.fn() });
    await vi.waitFor(() => expect(video.srcObject).toBeTruthy());
    scanner.stop();
    expect(stop).toHaveBeenCalled();
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

  it("play() 還在等待時呼叫 stop()，play() 解出後不再建立逐幀節流計時器", async () => {
    // 審查 Important 1：`stop()` 若發生在 `await video.play()` 這段等待期間
    // （真實瀏覽器要幾十到幾百毫秒才出第一幀，長輩可能就在這個空檔按「改用
    // 手動輸入」離開畫面），原始版本的計時器賦值寫在 `play()` 之後——`stop()`
    // 執行的當下 `timer` 還是 `null`，`if (timer !== null)` 不成立、什麼都
    // 沒清；等 `play()` 解出，程式碼繼續跑到建立 interval 那一行，一顆每
    // 167ms 觸發、持有整組 closure 的計時器就此永遠沒人記得清除。用手動
    // 控制的 Promise 製造「stop() 發生在 play() 還沒解出前」這個中間狀態。
    const stop = vi.fn();
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    const video = fakeVideo();
    let resolvePlay: (() => void) | null = null;
    video.play = vi.fn().mockReturnValue(
      new Promise<void>((resolve) => {
        resolvePlay = resolve;
      }),
    );
    const setIntervalFn = vi.fn().mockReturnValue(0);
    const clearIntervalFn = vi.fn();
    const scanner = createQrScanner({ video, onCode: vi.fn() }, { setIntervalFn, clearIntervalFn });
    await vi.waitFor(() => expect(video.srcObject).toBeTruthy()); // 已走到 play() 那一步
    scanner.stop(); // 使用者在 play() 還沒解出前就離開畫面
    resolvePlay!();
    await Promise.resolve();
    await Promise.resolve();
    expect(setIntervalFn).not.toHaveBeenCalled();
  });

  it("掃到碼只回報一次，不會因為連續幾幀都解出同一個碼而把呼叫端打爆", async () => {
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
      },
    });
    const onCode = vi.fn();
    const { schedule, cancel, waitForScheduled } = captureScheduler();
    createQrScanner(
      { video: fakeVideo(), onCode },
      {
        scanFrame: vi.fn().mockResolvedValue("kinsun://bind/abc123"),
        setIntervalFn: schedule,
        clearIntervalFn: cancel,
      },
    );
    const tick = await waitForScheduled();
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
    const { schedule, cancel, waitForScheduled } = captureScheduler();
    createQrScanner(
      { video: fakeVideo(), onCode },
      { scanFrame: vi.fn().mockResolvedValue(undefined), setIntervalFn: schedule, clearIntervalFn: cancel },
    );
    const tick = await waitForScheduled();
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
    const { schedule, cancel, waitForScheduled } = captureScheduler();
    const scanner = createQrScanner(
      { video: fakeVideo(), onCode },
      { scanFrame: vi.fn().mockReturnValue(scanPromise), setIntervalFn: schedule, clearIntervalFn: cancel },
    );
    const tick = await waitForScheduled();
    tick(); // 觸發一次解碼，尚未解出
    scanner.stop();
    expect(stop).toHaveBeenCalled(); // 停止當下軌道立刻釋放，不等解碼回來
    resolveScan!("kinsun://bind/abc123"); // 解碼終於回來，帶著一個有效的碼
    await scanPromise;
    await Promise.resolve(); // 讓 scanOnce() 內 await 之後的程式碼執行完
    expect(onCode).not.toHaveBeenCalled();
  });

  it("上一次解碼還沒回來時，逐幀節流不會疊加新的解碼", async () => {
    // 審查 Important 2：`setInterval` 不會等上一次 async 工作完成——wasm
    // 冷啟動（首次下載＋編譯，實測約 3～5 秒）期間，167ms 一次的節拍仍照打，
    // 若沒有防護會疊出十幾二十個同時在飛的 `scanFrame`（各自持有一張
    // 640×480 的 `ImageData`），wasm 一就緒就連續執行、把主執行緒卡住。
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
      },
    });
    let resolveScan: ((text: string | undefined) => void) | null = null;
    const scanPromise = new Promise<string | undefined>((resolve) => {
      resolveScan = resolve;
    });
    const scanFrame = vi.fn().mockReturnValue(scanPromise);
    const { schedule, cancel, waitForScheduled } = captureScheduler();
    createQrScanner(
      { video: fakeVideo(), onCode: vi.fn() },
      { scanFrame, setIntervalFn: schedule, clearIntervalFn: cancel },
    );
    const tick = await waitForScheduled();
    tick(); // 第一次解碼開始，尚未解出
    tick(); // 第二次節拍：上一次還沒回來
    tick(); // 第三次節拍：上一次還沒回來
    await Promise.resolve();
    expect(scanFrame).toHaveBeenCalledTimes(1);
    resolveScan!(undefined); // 收尾，避免測試留下未處理的 promise
  });

  it("非安全來源（不是 HTTPS 也不是 localhost）時回報 insecure-origin，不去要求相機權限", async () => {
    const getUserMedia = vi.fn();
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    const onError = vi.fn();
    createQrScanner({ video: fakeVideo(), onCode: vi.fn(), onError }, { isSecureContext: () => false });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith("insecure-origin"));
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it("沒有相機（NotFoundError）回報 not-found，與權限被拒分開", async () => {
    const error = new Error("no camera");
    error.name = "NotFoundError";
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(error) } });
    const onError = vi.fn();
    createQrScanner({ video: fakeVideo(), onCode: vi.fn(), onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith("not-found"));
  });

  it("相機被其他 App 佔用（NotReadableError）回報 in-use", async () => {
    const error = new Error("camera in use");
    error.name = "NotReadableError";
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(error) } });
    const onError = vi.fn();
    createQrScanner({ video: fakeVideo(), onCode: vi.fn(), onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith("in-use"));
  });

  it("play() 失敗（例如自動播放政策擋下）時回報 no-signal，並關閉相機軌道", async () => {
    const stop = vi.fn();
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) },
    });
    const video = fakeVideo();
    video.play = vi.fn().mockRejectedValue(new Error("NotAllowedError"));
    const onError = vi.fn();
    createQrScanner({ video, onCode: vi.fn(), onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith("no-signal"));
    expect(stop).toHaveBeenCalled();
  });

  it("開始播放後太久沒有第一幀畫面時，看門狗回報 no-signal", async () => {
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    });
    const video = fakeVideo({ videoWidth: 0 }); // 永遠沒有畫面
    const onError = vi.fn();
    const interval = captureScheduler();
    const watchdog = captureScheduler();
    createQrScanner(
      { video, onCode: vi.fn(), onError },
      {
        setIntervalFn: interval.schedule,
        clearIntervalFn: interval.cancel,
        setTimeoutFn: watchdog.schedule,
        clearTimeoutFn: watchdog.cancel,
      },
    );
    const fireWatchdog = await watchdog.waitForScheduled();
    fireWatchdog();
    expect(onError).toHaveBeenCalledWith("no-signal");
  });

  it("預設的 scanFrame 只建立一顆 canvas 重複使用，不會每一幀都新建一顆丟棄", async () => {
    // 審查 Minor 1：抽 `scanFrame` 注入點時，brief Step 5 原本把 canvas 提到
    // `scanOnce` 外面共用一顆的設計沒有一併保留——每秒丟棄 6 顆 640×480
    // canvas（各約 1.2 MB backing store）是未申報的第三處偏離，這裡補測試
    // 鎖住「只建立一次」這個不變量。不覆寫 `scanFrame`，用真正的預設實作
    // （jsdom 的 `canvas.getContext("2d")` 回 `null`，會在建立 canvas 之後、
    // 呼叫 wasm 之前就安全返回，不會真的跑到解碼）。
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    });
    const createElementSpy = vi.spyOn(document, "createElement");
    const { schedule, cancel, waitForScheduled } = captureScheduler();
    createQrScanner({ video: fakeVideo(), onCode: vi.fn() }, { setIntervalFn: schedule, clearIntervalFn: cancel });
    const tick = await waitForScheduled();
    const canvasCallsBeforeTicks = createElementSpy.mock.calls.filter(([tag]) => tag === "canvas").length;
    tick();
    await Promise.resolve();
    tick();
    await Promise.resolve();
    const canvasCallsAfterTicks = createElementSpy.mock.calls.filter(([tag]) => tag === "canvas").length;
    expect(canvasCallsAfterTicks - canvasCallsBeforeTicks).toBe(0);
    createElementSpy.mockRestore();
  });

  it("onCode 擲出例外不會讓掃描器自己的狀態卡死，改用 console.error 記錄", async () => {
    // 審查 Minor 4：呼叫端的 callback 若擲出，不能變成沒人接住的 unhandled
    // rejection，也不能完全靜默（那會讓呼叫端的臭蟲更難被發現）。這裡驗證
    // 兩件事：例外被 console.error 記下、去重旗標不受影響（再一次節拍不會
    // 再呼叫 onCode）。
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    });
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const onCode = vi.fn().mockImplementation(() => {
      throw new Error("呼叫端的臭蟲");
    });
    const { schedule, cancel, waitForScheduled } = captureScheduler();
    createQrScanner(
      { video: fakeVideo(), onCode },
      { scanFrame: vi.fn().mockResolvedValue("kinsun://bind/abc123"), setIntervalFn: schedule, clearIntervalFn: cancel },
    );
    const tick = await waitForScheduled();
    tick();
    await vi.waitFor(() => expect(onCode).toHaveBeenCalledTimes(1));
    expect(errorSpy).toHaveBeenCalled();
    tick(); // 再一次節拍：去重仍然生效，不會再呼叫 onCode
    await Promise.resolve();
    expect(onCode).toHaveBeenCalledTimes(1);
    errorSpy.mockRestore();
  });
});
