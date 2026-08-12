/** 瀏覽器錄音。用假的 MediaRecorder 與 getUserMedia，測試完全不碰真麥克風。 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { createRecorder, probeMicrophone } from "./recorder";

class FakeMediaRecorder {
  static lastInstance: FakeMediaRecorder | null = null;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  state = "inactive";
  /** 真的 MediaRecorder 會在 start() 之後給出實際採用的容器格式。 */
  mimeType = "audio/webm;codecs=opus";

  constructor(public stream: unknown) {
    FakeMediaRecorder.lastInstance = this;
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2, 3])]) });
    this.onstop?.();
  }
}

function stubBrowser(options: { denied?: boolean } = {}) {
  const stop = vi.fn();
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("navigator", {
    mediaDevices: {
      getUserMedia: options.denied
        ? vi.fn().mockRejectedValue(new Error("NotAllowedError"))
        : vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
    },
  });
  return { stop };
}

afterEach(() => vi.unstubAllGlobals());

describe("createRecorder", () => {
  it("開始錄音回報成功", async () => {
    stubBrowser();
    const recorder = createRecorder();
    expect(await recorder.start()).toBe(true);
    expect(recorder.isRecording()).toBe(true);
  });

  it("使用者拒絕麥克風時回 false，不擲例外", async () => {
    // 擲出去的話，長輩端整個畫面會白掉——他連「重試」的按鈕都看不到。
    stubBrowser({ denied: true });
    const recorder = createRecorder();
    expect(await recorder.start()).toBe(false);
    expect(recorder.isRecording()).toBe(false);
  });

  it("停止後拿得到錄到的位元組", async () => {
    stubBrowser();
    const recorder = createRecorder();
    await recorder.start();
    const bytes = await recorder.stop();
    expect(bytes).toBeInstanceOf(ArrayBuffer);
    expect(bytes!.byteLength).toBe(3);
  });

  it("停止時關掉麥克風軌道，不讓瀏覽器一直亮著錄音指示燈", async () => {
    const { stop } = stubBrowser();
    const recorder = createRecorder();
    await recorder.start();
    await recorder.stop();
    expect(stop).toHaveBeenCalled();
  });

  it("沒在錄音時停止回 null，不當掉", async () => {
    stubBrowser();
    expect(await createRecorder().stop()).toBeNull();
  });

  it("MediaRecorder 建立失敗時仍要關掉已取得的麥克風軌道，不留殘留指示燈", async () => {
    // 找到的問題（brief 未涵蓋）：getUserMedia 成功後，若 `new MediaRecorder(stream)`
    // 這一行才失敗（例如瀏覽器不支援某些設定），brief 原始的 catch 區塊只把
    // `stream` 參考設成 null，從沒呼叫 `track.stop()`——麥克風其實還開著、
    // 指示燈仍亮，跟本工項要防的第一種錯一模一樣。
    const stop = vi.fn();
    vi.stubGlobal(
      "MediaRecorder",
      class {
        constructor() {
          throw new Error("此設定不受支援");
        }
      },
    );
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    const recorder = createRecorder();
    expect(await recorder.start()).toBe(false);
    expect(stop).toHaveBeenCalled();
  });

  it("start() 飛行中（等待權限）時重入，第二次呼叫直接回 false，不覆蓋第一顆 stream", async () => {
    // 審查發現的問題：`recorder` 只在 await getUserMedia 之後才賦值，等待
    // 權限的整個窗口裡 isRecording() 回 false，呼叫端就算檢查也擋不住重入
    // ——沒有這道保護，第二次 start() 會覆蓋 stream 變數，讓第一顆
    // MediaStream 的軌道從此沒有人呼叫 track.stop()。
    let resolveGetUserMedia: ((stream: unknown) => void) | null = null;
    const firstStop = vi.fn();
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockReturnValue(
          new Promise((resolve) => {
            resolveGetUserMedia = resolve;
          }),
        ),
      },
    });
    const recorder = createRecorder();
    const firstStart = recorder.start(); // 飛行中，getUserMedia 尚未解出
    expect(await recorder.start()).toBe(false); // 重入：立即回 false，不等待
    resolveGetUserMedia!({ getTracks: () => [{ stop: firstStop }] });
    expect(await firstStart).toBe(true);
  });

  it("MediaRecorder.stop() 同步擲出例外時仍能收尾、關閉麥克風軌道，不讓例外冒出去呼叫端", async () => {
    // 審查發現的問題：`active.stop()` 依規格在非 recording／paused 狀態呼叫
    // 會同步擲出 InvalidStateError（例如錄音途中來電／Siri 介入／藍牙耳機
    // 被拔，系統把軌道搶走、MediaRecorder 已自行回到 inactive，長輩這時才
    // 放開按鈕）。擲出去的話跟 start() 同一個理由——呼叫端沒接住就整個畫面
    // 白掉。
    class ThrowingMediaRecorder extends FakeMediaRecorder {
      override stop() {
        throw new Error("InvalidStateError");
      }
    }
    const stop = vi.fn();
    vi.stubGlobal("MediaRecorder", ThrowingMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    const recorder = createRecorder();
    await recorder.start();
    const bytes = await recorder.stop();
    expect(bytes).toBeInstanceOf(ArrayBuffer);
    expect(stop).toHaveBeenCalled();
    expect(recorder.isRecording()).toBe(false);
  });

  it("onstop 事件真的沒來時，保險逾時後仍然收尾並關閉麥克風軌道", async () => {
    // 審查發現的問題：事件真的沒來時（同一種系統搶走軌道的情境），沒有
    // 保險逾時，這個 Promise 永遠不 resolve——長輩按了停止鍵卻沒有任何
    // 反應，呼叫端會永遠卡在 await 上。
    class HangingMediaRecorder extends FakeMediaRecorder {
      override stop() {
        this.state = "inactive";
        // 刻意不觸發 ondataavailable／onstop：模擬事件真的不來的情境。
      }
    }
    const stop = vi.fn();
    vi.stubGlobal("MediaRecorder", HangingMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    let fireGuard: (() => void) | null = null;
    const recorder = createRecorder({
      setTimeoutFn: (fn) => {
        fireGuard = fn;
        return 0 as never;
      },
      clearTimeoutFn: () => {},
    });
    await recorder.start();
    const stopPromise = recorder.stop();
    fireGuard!(); // 手動觸發保險逾時（onstop 從未呼叫）
    const bytes = await stopPromise;
    expect(bytes).toBeInstanceOf(ArrayBuffer);
    expect(stop).toHaveBeenCalled();
  });

  it("錄完之後仍取得得到錄音的容器格式——stop() 會把 Blob 的 type 丟掉", async () => {
    stubBrowser();
    const recorder = createRecorder();
    await recorder.start();
    await recorder.stop();
    // ⚠️ 在 stop() **之後**問：呼叫端（客製化聲音上傳）要拿它當 Content-Type，
    // 而那一定發生在停止之後；stop() 內部會把 recorder 參考清成 null。
    expect(recorder.mimeType()).toBe("audio/webm;codecs=opus");
  });

  it("瀏覽器沒回報格式時退回 audio/webm，不送出空的 Content-Type", async () => {
    // 後端檢查 content-type.startsWith("audio/")，空字串會拿到 415。
    class SilentMediaRecorder extends FakeMediaRecorder {
      mimeType = "";
    }
    vi.stubGlobal("MediaRecorder", SilentMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
      },
    });
    const recorder = createRecorder();
    await recorder.start();
    await recorder.stop();
    expect(recorder.mimeType()).toBe("audio/webm");
  });
});

describe("probeMicrophone", () => {
  it("拿得到麥克風時回 granted，並立刻把軌道關掉", async () => {
    // ⚠️ 探測完不關軌道的話，分頁上的錄音指示燈從進畫面就一直亮著——長輩會
    // 以為金孫在偷聽，而他其實還沒按過任何按鈕。
    const { stop } = stubBrowser();
    expect(await probeMicrophone({ isSecureContext: () => true })).toBe("granted");
    expect(stop).toHaveBeenCalled();
  });

  it.each([
    ["NotAllowedError", "denied"],
    ["NotFoundError", "not-found"],
    ["NotReadableError", "in-use"],
    ["SomethingWeirdError", "denied"],
  ])("getUserMedia 擲出 %s 時分類成 %s", async (name, expected) => {
    // 「NotFoundError」對長輩沒有意義。四種成因要對到四句不同的「下一步做什麼」
    //（沒有麥克風的桌機不必去找權限開關），下游文案才有辦法講對。
    const error = new Error(name);
    error.name = name;
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(error) },
    });
    expect(await probeMicrophone({ isSecureContext: () => true })).toBe(expected);
  });

  it("網址不是安全來源時回 insecure-origin，而且完全不去碰 getUserMedia", async () => {
    // 區網 IP 直連（http://192.168.x.x，組員自測最常見）在瀏覽器裡連
    // navigator.mediaDevices 都不會有——講「換一家瀏覽器」是錯的方向，要換網址。
    const getUserMedia = vi.fn();
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    expect(await probeMicrophone({ isSecureContext: () => false })).toBe("insecure-origin");
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it("瀏覽器沒有 getUserMedia 時回 unsupported，不擲例外", async () => {
    vi.stubGlobal("navigator", { mediaDevices: undefined });
    expect(await probeMicrophone({ isSecureContext: () => true })).toBe("unsupported");
  });
});
