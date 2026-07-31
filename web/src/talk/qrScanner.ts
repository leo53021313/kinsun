/**
 * 相機掃 QR（長輩端配對用）。
 *
 * ⚠️ **不用瀏覽器原生的 `BarcodeDetector`**：那只有 Chrome 系有，Safari 與
 * Firefox 沒有。W-15 要求全瀏覽器可用，所以走 WebAssembly 版的 ZXing。
 *
 * ⚠️ **wasm 必須由自己的網域提供**。套件預設會去 jsDelivr CDN 抓，而後端 CSP 的
 * `default-src 'self'` 會擋掉——症狀是掃碼完全沒反應、只有主控台一行紅字，
 * 從畫面上完全看不出是被政策擋的。
 *
 * ⚠️ **修正計畫假設與套件實際 API 的落差**：`zxing-wasm@3.1.2` 沒有
 * `overrideWasmUrl` 這個選項（讀套件型別定義與 README 確認）。要覆寫 wasm
 * 位址得透過 `prepareZXingModule({ overrides: { locateFile } })`——
 * `locateFile` 是 Emscripten Module 的標準掛鉤，套件內建的 CDN 位址本身也是
 * 靠覆寫這個函式做到的（見套件 README「Serving via Web or CDN」一節）。
 *
 * ⚠️ 相機要求 HTTPS（`localhost` 除外）。與麥克風同一個限制；區域網路 IP
 * 直連（如 `http://192.168.x.x`）會整個拿不到相機，須走 ngrok／Cloudflare
 * 隧道等 HTTPS 來源——回報為 `"insecure-origin"`，與單純「瀏覽器不支援」
 * 分開，下游文案才有辦法講清楚「換網址」而非「換瀏覽器」。
 *
 * ⚠️ **呼叫端契約**：傳入的 `video` 元素應設定 `playsInline`／`muted`——
 * 本模組會呼叫 `video.play()`，若 `video` 沒有 `playsInline`，iOS Safari
 * 會把畫面全螢幕跳出而非留在原位；沒有 `muted`，部分瀏覽器的自動播放政策
 * 會直接讓 `play()` reject（本模組收到後回報 `"no-signal"`，但體驗仍不如
 * 一開始就設對屬性）。這兩個屬性由呼叫端在建立 `<video>` 時設定，本模組
 * 不代為設定（避免對一個外部傳入的 DOM 節點做出呼叫端沒預期到的修改）。
 *
 * jsdom 沒有 canvas 也沒有 WebAssembly 執行環境，實際的畫面擷取與解碼因此藏在
 * `scanFrame`（見 `QrScannerDeps`）這個注入點後面——預設走真正的
 * canvas＋zxing-wasm，測試餵假的解碼結果進來，測的是本檔自己的邏輯（去重、
 * 停止後不再回報、逐幀節流不疊層、相機軌道釋放），不是相機或 wasm 本身。
 */

import { prepareZXingModule, readBarcodes } from "zxing-wasm/reader";

/**
 * wasm 與本頁同源。用 `import.meta.env.BASE_URL` 而非寫死 `"/demo/"`——
 * `vite.config.ts` 的 `base` 一改，這裡自動跟著變，不必兩處同步（審查
 * 發現：寫死字面值的話，`base` 改掉只會在執行期以「掃碼完全沒反應」的
 * 方式靜默失敗，不會有任何編譯期或建置期的錯誤訊息）。
 */
prepareZXingModule({
  overrides: {
    locateFile: (path: string) => `${import.meta.env.BASE_URL}${path}`,
  },
});

/** 每秒解碼幾次。太密會吃滿 CPU 讓畫面卡，太疏長輩會覺得掃不到。 */
const SCANS_PER_SECOND = 6;

/**
 * 相機拿到權限後，等這麼久都還沒看到第一幀畫面（`videoWidth > 0`）就回報
 * `"no-signal"`。留足夠緩衝給 wasm 冷啟動（首次下載＋編譯約 1.02 MiB）與
 * 相機初始化，同時不讓長輩對著黑框枯等到懷疑人生。
 */
const FIRST_FRAME_TIMEOUT_MS = 8000;

/**
 * - `"denied"`：使用者明確拒絕相機權限（或無法歸類的其他失敗原因，安全預設）。
 * - `"not-found"`：裝置沒有相機（`NotFoundError`）——長輩不必去開權限，去開也沒用。
 * - `"in-use"`：相機被別的 App 佔用（`NotReadableError`）——手機上很常見。
 * - `"insecure-origin"`：目前網址不是安全來源（非 HTTPS 且非 `localhost`）——
 *   瀏覽器本身沒問題，是網址不對，需要換用家人提供的 HTTPS 網址。
 * - `"no-signal"`：拿到相機權限了，但一直看不到畫面——`play()` 失敗，或超過
 *   `FIRST_FRAME_TIMEOUT_MS` 仍沒有第一幀，常見成因是硬體問題、鏡頭被物理
 *   遮蔽、或系統把相機工作階段搶走。
 * - `"unsupported"`：瀏覽器沒有 `getUserMedia` API。
 */
export type QrScannerError = "denied" | "not-found" | "in-use" | "insecure-origin" | "no-signal" | "unsupported";

/**
 * setInterval／setTimeout 的回傳值在不同環境型別不同（`web/tsconfig.json`
 * 同時載入 `DOM`／`node`），這裡只當成不透明代號傳來傳去（同 `recorder.ts`
 * 的 `StopGuardHandle`、`talkSocket.ts` 的 `RetryHandle` 既有慣例）。
 */
type TimerHandle = number | ReturnType<typeof setInterval>;

/** 注入點：測試不想真的擷取畫面／跑 wasm（同 `recorder.ts` 的既有慣例）。 */
export type QrScannerDeps = {
  /**
   * 從目前這格畫面解出條碼文字。預設實作＝canvas 擷取一幀＋zxing-wasm 解碼；
   * 回傳 `undefined` 代表這一幀沒讀到東西——單幀解不出來是常態（手在抖、
   * 對焦中），呼叫端不記 log、不當錯誤處理。
   */
  scanFrame?: (video: HTMLVideoElement) => Promise<string | undefined>;
  /** 逐幀節流計時器注入點：測試手動觸發，不必真的等 1000/6 毫秒。 */
  setIntervalFn?: (fn: () => void, ms: number) => TimerHandle;
  clearIntervalFn?: (handle: TimerHandle) => void;
  /** 保險逾時（第一幀看門狗）注入點：測試手動觸發，不必真的等 8 秒。 */
  setTimeoutFn?: (fn: () => void, ms: number) => TimerHandle;
  clearTimeoutFn?: (handle: TimerHandle) => void;
  /**
   * 是否為安全來源。預設讀 `window.isSecureContext`；jsdom 沒有實作這個
   * 屬性（回傳 `undefined`），故 `?? true` 作為測試環境的安全網——真實
   * 瀏覽器一律會給出明確的 `true`／`false`，這個退避值在正式環境不會被
   * 觸發到。
   */
  isSecureContext?: () => boolean;
};

/**
 * canvas 只建立一顆、重複使用（brief Step 5 的原始設計）。若每一幀都
 * `document.createElement("canvas")`，每秒六次配置又丟棄一顆 640×480 的
 * 畫布（約 1.2 MB backing store／次），在低階手機上是實質的 GC 壓力——
 * 審查發現這是抽 `scanFrame` 注入點時未申報的偏離，已修正。
 */
function createDefaultScanFrame(): (video: HTMLVideoElement) => Promise<string | undefined> {
  const canvas = document.createElement("canvas");
  return async function scanFrame(video: HTMLVideoElement): Promise<string | undefined> {
    if (video.videoWidth === 0) {
      // 相機畫面還沒有第一幀（例如 `play()` 剛開始還在緩衝），此時擷取只會
      // 拿到一張全黑畫布，白白耗一次解碼。
      return undefined;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (context === null) {
      return undefined;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    try {
      const results = await readBarcodes(context.getImageData(0, 0, canvas.width, canvas.height), {
        formats: ["QRCode"],
      });
      return results[0]?.text;
    } catch {
      // 單幀解不出來是常態（手在抖、對焦中）。不記 log——每秒六次的雜訊會把
      // 真正有用的訊息淹掉。
      return undefined;
    }
  };
}

/** `getUserMedia` 拒絕時，把瀏覽器的 `DOMException.name` 對應到白話分類。 */
function classifyGetUserMediaError(error: unknown): QrScannerError {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "not-found";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "in-use";
  }
  // 涵蓋 NotAllowedError（使用者拒絕）與其他無法歸類的成因；「denied」是
  // 最安全的預設——大多數不明成因也是引導使用者去檢查權限設定。
  return "denied";
}

/**
 * 呼叫端的 callback（`onCode`／`onError`）若擲出，不能讓例外卡在本模組的
 * async 呼叫鏈裡變成沒人接住的 unhandled rejection，也不能完全靜默——那是
 * 呼叫端自己的臭蟲，吞掉只會讓它更難被發現。只印出來、不重新擲出：
 * `void scanOnce()` 呼叫端本來就不等這個 Promise，重新擲出只會變成另一種
 * 形式的「未捕捉例外」，對除錯能見度沒有本質差異，但不會有意外把整條
 * microtask 佇列炸掉的風險。
 */
function invokeCallback(run: () => void): void {
  try {
    run();
  } catch (error) {
    console.error("[qrScanner] 呼叫端 callback 擲出例外", error);
  }
}

export function createQrScanner(
  options: {
    video: HTMLVideoElement;
    onCode: (text: string) => void;
    onError?: (reason: QrScannerError) => void;
  },
  deps: QrScannerDeps = {},
): { stop: () => void } {
  const { video, onCode, onError } = options;
  const {
    scanFrame = createDefaultScanFrame(),
    setIntervalFn = setInterval,
    clearIntervalFn = clearInterval,
    setTimeoutFn = setTimeout,
    clearTimeoutFn = clearTimeout,
    isSecureContext = () => window.isSecureContext ?? true,
  } = deps;
  let stream: MediaStream | null = null;
  let timer: TimerHandle | null = null;
  let firstFrameWatchdog: TimerHandle | null = null;
  let stopped = false;
  // 同一個碼在連續幾幀裡都會被讀到；只回報第一次，否則呼叫端會被打爆。
  // 刻意不在回報後清掉 timer——由呼叫端收到 onCode 後自行決定何時 stop()，
  // 這段空窗期間每幀都會被下面這行擋掉，不會白白重複解碼觸發 onCode。
  let reported = false;
  // 上一次解碼還沒回來時，這一幀直接跳過——沒有這道防護，wasm 冷啟動（首次
  // 下載＋編譯，實測約 3～5 秒）期間 `setInterval` 仍照打，會疊出十幾二十個
  // 同時在飛的 `scanFrame`（各自持有一張 640×480 的 `ImageData`，等 wasm
  // 就緒後又連續執行，把主執行緒卡住、畫面凍住）。
  let inFlight = false;
  let firstFrameSeen = false;

  function clearFirstFrameWatchdog() {
    if (firstFrameWatchdog !== null) {
      clearTimeoutFn(firstFrameWatchdog);
      firstFrameWatchdog = null;
    }
  }

  async function scanOnce() {
    if (stopped || reported || inFlight) {
      return;
    }
    if (!firstFrameSeen && video.videoWidth > 0) {
      firstFrameSeen = true;
      clearFirstFrameWatchdog();
    }
    inFlight = true;
    try {
      const text = await scanFrame(video);
      // ⚠️ 修正 brief 原始版本的缺陷：解碼期間（`await scanFrame` 這段）使用者
      // 若呼叫 `stop()`，原始版本回來後只重新檢查 `!reported`、沒有重新檢查
      // `stopped`——相機軌道明明已經關了，飛行中的解碼卻仍可能在那之後才解出
      // 東西，把已經離開這個畫面的呼叫端打醒。見 qrScanner.test.ts「解碼還在
      // 飛行中被 stop()」。
      if (text && !stopped && !reported) {
        reported = true;
        invokeCallback(() => onCode(text));
      }
    } finally {
      inFlight = false;
    }
  }

  void (async () => {
    if (!isSecureContext()) {
      invokeCallback(() => onError?.("insecure-origin"));
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      invokeCallback(() => onError?.("unsupported"));
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        // 後鏡頭：長輩是拿手機去對家人螢幕上的 QR。
        video: { facingMode: "environment" },
      });
    } catch (error) {
      invokeCallback(() => onError?.(classifyGetUserMediaError(error)));
      return;
    }
    if (stopped) {
      // 相機權限視窗還沒回來，使用者就已經離開畫面：拿到的軌道還是要關掉，
      // 不然指示燈會一直亮著。
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    video.srcObject = stream;
    try {
      await video.play();
    } catch {
      // ⚠️ 修正缺陷：原本吞掉 `play()` 的失敗（自動播放政策、來電中斷等）。
      // 吞掉的後果——interval 照樣建立、`videoWidth` 永遠是 0、長輩對著黑框
      // 掃到天荒地老，畫面上沒有任何錯誤訊息，相機指示燈卻全程亮著。
      invokeCallback(() => onError?.("no-signal"));
      stream?.getTracks().forEach((track) => track.stop());
      stream = null;
      return;
    }
    if (stopped) {
      // ⚠️ 修正缺陷：`stop()` 若發生在 `await video.play()` 這段等待期間，
      // `stream` 當時已經賦值，`stop()` 自己的軌道釋放已經執行過——這裡只需
      // 避免在那之後才建立一個永遠沒人清除的 interval／看門狗（原版本會在
      // `stop()` 執行完畢後才把 timer 賦值，`stop()` 內 `if (timer !== null)`
      // 因此永遠不成立，這顆計時器就此活到頁面關閉為止）。
      return;
    }
    timer = setIntervalFn(() => void scanOnce(), 1000 / SCANS_PER_SECOND);
    firstFrameWatchdog = setTimeoutFn(() => {
      if (!firstFrameSeen) {
        invokeCallback(() => onError?.("no-signal"));
      }
    }, FIRST_FRAME_TIMEOUT_MS);
  })();

  return {
    stop() {
      stopped = true;
      try {
        if (timer !== null) {
          clearIntervalFn(timer);
          timer = null;
        }
        clearFirstFrameWatchdog();
      } finally {
        // 不關軌道的話相機燈會一直亮著。
        stream?.getTracks().forEach((track) => track.stop());
        stream = null;
      }
    },
  };
}
