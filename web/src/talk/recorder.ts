/**
 * 瀏覽器錄音（取代 App 的 expo-audio）。
 *
 * ⚠️ 錄出來的容器格式各家不同：Chrome／Firefox 給 webm/opus，Safari 給 mp4/aac。
 * **後端不需要處理**——ASR 是寫暫存檔後交給 ffmpeg 解容器（`services/asr/server.py`
 * 的 `_decode_to_mono16k`），兩種都吃。但驗收必須跨三家瀏覽器實測，不可只測 Chrome。
 *
 * ⚠️ 麥克風只在 HTTPS 下可用。`localhost` 有安全例外，所以本機測試會給出假的
 * 安全感——驗收要在真的 ngrok 網址上做。
 */

export type Recorder = {
  /** 開始錄音；回傳是否真的開始（權限被拒、瀏覽器不支援都回 false）。 */
  start: () => Promise<boolean>;
  /** 停止並取回錄到的位元組；沒在錄音時回 null。 */
  stop: () => Promise<ArrayBuffer | null>;
  isRecording: () => boolean;
};

/**
 * setTimeout 的回傳值在不同環境型別不同，這裡只當成不透明代號傳來傳去
 * （同 `talkSocket.ts` 的 `RetryHandle`，此檔刻意不 import 該型別以維持零
 * 依賴，見 09_模組依賴關係）。
 */
type StopGuardHandle = number | ReturnType<typeof setTimeout>;

/**
 * `stop()` 等待 `onstop` 事件的保險逾時（毫秒）。
 *
 * ⚠️ 事件真的沒來時（例如系統把麥克風軌道搶走、`MediaRecorder` 已自行回到
 * `"inactive"`），沒有這個保險就是這個 Promise **永遠不 resolve**——長輩按了
 * 停止鍵卻沒有任何反應，呼叫端（未來 Task 8 的 `stopAndSend`）會卡在
 * `await` 上。與 `talkSocket.ts::playAndWait` 的保險逾時同一種理由。
 */
const STOP_GUARD_MS = 3000;

/** 注入點：測試不想真的等（同 `talkSocket.ts` 的既有慣例）。 */
export type RecorderDeps = {
  setTimeoutFn?: (fn: () => void, ms: number) => StopGuardHandle;
  clearTimeoutFn?: (handle: StopGuardHandle) => void;
};

export function createRecorder(deps: RecorderDeps = {}): Recorder {
  const { setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout } = deps;
  let recorder: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  let chunks: Blob[] = [];
  // 重入保護：`recorder` 只在 `await getUserMedia` 之後才賦值，等待權限的
  // 整個窗口裡 `isRecording()` 回 false，呼叫端就算檢查也擋不住重入——第二次
  // `start()` 會覆蓋 `stream`／`recorder` 變數，讓第一顆 `MediaStream` 的軌道
  // 從此沒有人呼叫 `track.stop()`，指示燈永遠關不掉。
  let starting = false;

  return {
    async start() {
      if (starting || recorder !== null) {
        return false;
      }
      starting = true;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            chunks.push(event.data);
          }
        };
        recorder.start();
        return true;
      } catch {
        // 權限被拒或瀏覽器不支援都走這裡。⚠️ 不擲出去——擲出去的話長輩端整個
        // 畫面會白掉，他連「重試」的按鈕都看不到。呼叫端據回傳值顯示白話說明。
        //
        // ⚠️ 修正 brief 原始版本的資源洩漏：`getUserMedia` 可能已經成功取得
        // 麥克風軌道，只是之後 `new MediaRecorder(stream)` 才失敗（例如瀏覽器
        // 不支援某個設定）。原本這裡只把 `stream` 參考設成 null，從沒關掉
        // 軌道——麥克風其實還開著、指示燈仍亮，跟本工項要防的第一種錯一模
        // 一樣。見 recorder.test.ts「MediaRecorder 建立失敗時仍要關掉已取得的
        // 麥克風軌道」。
        stream?.getTracks().forEach((track) => track.stop());
        stream = null;
        recorder = null;
        return false;
      } finally {
        starting = false;
      }
    },

    async stop() {
      const active = recorder;
      if (active === null) {
        return null;
      }
      // ⚠️ 關掉軌道與重置狀態放進 finally：`active.stop()` 依 MediaRecorder
      // 規格，在非 "recording"／"paused" 狀態呼叫會同步擲出
      // `InvalidStateError`——例如錄音途中來電／Siri 介入／藍牙耳機被拔，
      // 系統把軌道搶走、`MediaRecorder` 已自行回到 `"inactive"`，長輩這時
      // 放開按鈕才呼叫 `stop()`。若軌道關閉與狀態重置寫在這段之後，這條
      // 路徑會整段跳過——麥克風指示燈永遠關不掉（跟本檔第一段要防的事一
      // 模一樣），`isRecording()` 也永遠回 `true`。`finally` 保證無論成功、
      // 同步擲出例外、或保險逾時，這兩件事都會發生。
      try {
        return await new Promise<ArrayBuffer>((resolve) => {
          let settled = false;
          let guard: StopGuardHandle | null = null;
          const finish = () => {
            if (settled) return;
            settled = true;
            if (guard !== null) clearTimeoutFn(guard);
            void new Blob(chunks).arrayBuffer().then(resolve);
          };
          // 保險逾時：見上方 STOP_GUARD_MS 說明。
          guard = setTimeoutFn(finish, STOP_GUARD_MS);
          active.onstop = finish;
          try {
            active.stop();
          } catch {
            // `active.stop()` 本身同步擲出（如 `InvalidStateError`）：手上
            // 已有的 chunks 仍然有效，直接用它們收尾，不必等 onstop 或保險
            // 逾時。這層內層 catch 已經保證這個 Promise 不會 reject——下面
            // 的 `finally` 因此目前沒有「與內層 catch 不同」的可獨立驗證
            // 路徑，屬於防禦性寫法：保護日後若有人在這個 executor 裡加入
            // 新的、未被內層 catch 涵蓋的擲出路徑時，軌道關閉與狀態重置仍
            // 不會被跳過（見 task-4-report.md 對這一層的誠實記載）。
            finish();
          }
        });
      } finally {
        // ⚠️ 關掉軌道：不關的話瀏覽器分頁上的錄音指示燈會一直亮著，長輩（與展示
        // 現場的觀眾）會以為它在偷聽。
        stream?.getTracks().forEach((track) => track.stop());
        stream = null;
        recorder = null;
      }
    },

    isRecording() {
      return recorder !== null;
    },
  };
}
