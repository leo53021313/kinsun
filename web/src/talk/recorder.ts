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

export function createRecorder(): Recorder {
  let recorder: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  let chunks: Blob[] = [];

  return {
    async start() {
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
      }
    },

    async stop() {
      const active = recorder;
      if (active === null) {
        return null;
      }
      const bytes = await new Promise<ArrayBuffer>((resolve) => {
        active.onstop = () => {
          void new Blob(chunks).arrayBuffer().then(resolve);
        };
        active.stop();
      });
      // ⚠️ 關掉軌道：不關的話瀏覽器分頁上的錄音指示燈會一直亮著，長輩（與展示
      // 現場的觀眾）會以為它在偷聽。
      stream?.getTracks().forEach((track) => track.stop());
      stream = null;
      recorder = null;
      return bytes;
    },

    isRecording() {
      return recorder !== null;
    },
  };
}
