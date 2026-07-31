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
 * 隧道等 HTTPS 來源。
 *
 * jsdom 沒有 canvas 也沒有 WebAssembly 執行環境，實際的畫面擷取與解碼因此藏在
 * `scanFrame`（見 `QrScannerDeps`）這個注入點後面——預設走真正的
 * canvas＋zxing-wasm，測試餵假的解碼結果進來，測的是本檔自己的邏輯（去重、
 * 停止後不再回報、相機軌道釋放），不是相機或 wasm 本身。
 */

import { prepareZXingModule, readBarcodes } from "zxing-wasm/reader";

/** wasm 與本頁同源，路徑與 vite.config 的 base（"/demo/"）一致。 */
prepareZXingModule({
  overrides: {
    locateFile: (path: string) => `/demo/${path}`,
  },
});

/** 每秒解碼幾次。太密會吃滿 CPU 讓畫面卡，太疏長輩會覺得掃不到。 */
const SCANS_PER_SECOND = 6;

export type QrScannerError = "denied" | "unsupported";

/**
 * setInterval 的回傳值在不同環境型別不同（`web/tsconfig.json` 同時載入
 * `DOM`／`node`），這裡只當成不透明代號傳來傳去（同 `recorder.ts` 的
 * `StopGuardHandle`、`talkSocket.ts` 的 `RetryHandle` 既有慣例）。
 */
type IntervalHandle = number | ReturnType<typeof setInterval>;

/** 注入點：測試不想真的擷取畫面／跑 wasm（同 `recorder.ts` 的既有慣例）。 */
export type QrScannerDeps = {
  /**
   * 從目前這格畫面解出條碼文字。預設實作＝canvas 擷取一幀＋zxing-wasm 解碼；
   * 回傳 `undefined` 代表這一幀沒讀到東西——單幀解不出來是常態（手在抖、
   * 對焦中），呼叫端不記 log、不當錯誤處理。
   */
  scanFrame?: (video: HTMLVideoElement) => Promise<string | undefined>;
  /** 逐幀節流計時器注入點：測試手動觸發，不必真的等 1000/6 毫秒。 */
  setIntervalFn?: (fn: () => void, ms: number) => IntervalHandle;
  clearIntervalFn?: (handle: IntervalHandle) => void;
};

async function defaultScanFrame(video: HTMLVideoElement): Promise<string | undefined> {
  if (video.videoWidth === 0) {
    // 相機畫面還沒有第一幀（例如 `play()` 剛開始還在緩衝），此時擷取只會
    // 拿到一張全黑畫布，白白耗一次解碼。
    return undefined;
  }
  const canvas = document.createElement("canvas");
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
  const { scanFrame = defaultScanFrame, setIntervalFn = setInterval, clearIntervalFn = clearInterval } = deps;
  let stream: MediaStream | null = null;
  let timer: IntervalHandle | null = null;
  let stopped = false;
  // 同一個碼在連續幾幀裡都會被讀到；只回報第一次，否則呼叫端會被打爆。
  // 刻意不在回報後清掉 timer——由呼叫端收到 onCode 後自行決定何時 stop()，
  // 這段空窗期間每幀都會被下面這行擋掉，不會白白重複解碼觸發 onCode。
  let reported = false;

  async function scanOnce() {
    if (stopped || reported) {
      return;
    }
    const text = await scanFrame(video);
    // ⚠️ 修正 brief 原始版本的缺陷：解碼期間（`await scanFrame` 這段）使用者
    // 若呼叫 `stop()`，原始版本回來後只重新檢查 `!reported`、沒有重新檢查
    // `stopped`——相機軌道明明已經關了，飛行中的解碼卻仍可能在那之後才解出
    // 東西，把已經離開這個畫面的呼叫端打醒。見 qrScanner.test.ts「解碼還在
    // 飛行中被 stop()」。
    if (text && !stopped && !reported) {
      reported = true;
      onCode(text);
    }
  }

  void (async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      onError?.("unsupported");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        // 後鏡頭：長輩是拿手機去對家人螢幕上的 QR。
        video: { facingMode: "environment" },
      });
    } catch {
      onError?.("denied");
      return;
    }
    if (stopped) {
      // 相機權限視窗還沒回來，使用者就已經離開畫面：拿到的軌道還是要關掉，
      // 不然指示燈會一直亮著。
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    video.srcObject = stream;
    await video.play().catch(() => undefined);
    timer = setIntervalFn(() => void scanOnce(), 1000 / SCANS_PER_SECOND);
  })();

  return {
    stop() {
      stopped = true;
      if (timer !== null) {
        clearIntervalFn(timer);
        timer = null;
      }
      // 不關軌道的話相機燈會一直亮著。
      stream?.getTracks().forEach((track) => track.stop());
      stream = null;
    },
  };
}
