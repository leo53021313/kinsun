/**
 * 家屬錄製參考語音的狀態機。
 *
 * 抽成 hook 而不是寫在畫面裡：它管的三件事（計時、最短長度門檻、資源回收）都是
 * 「壞掉不會噴錯」的類型，混在畫面裡就只能靠點畫面來測。
 *
 * ⚠️ **最短長度門檻不是體感問題**：稿子沒唸完＝逐字稿對不上音檔，合成品質會
 * 靜默壞掉（`voice_profiles/script.py` 檔頭）。門檻值必須跟著稿子長度走：
 * 2026-08-19 稿子從 40 字換成 16 字（滲漏修正，見 SCRIPT_RATIONALE），
 * 門檻同步從 8 秒調成 4 秒。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { createRecorder, type Recorder } from "@/talk/recorder";

/** 低於這個長度不讓送出。16 字的稿子自然語速約 5～7 秒，4 秒是「明顯沒唸完」的界線。 */
export const MIN_RECORDING_MS = 4000;

/** 錄音中更新秒數的間隔。 */
const TICK_MS = 100;

export type VoiceRecordingStatus = "idle" | "recording" | "recorded";

/** 注入點：測試不碰真麥克風、不依賴真時鐘，且 jsdom 沒有 `URL.createObjectURL`。 */
export type VoiceRecordingDeps = {
  createRecorderFn?: () => Recorder;
  now?: () => number;
  createObjectUrl?: (blob: Blob) => string;
  revokeObjectUrl?: (uri: string) => void;
};

export function useVoiceRecording(deps: VoiceRecordingDeps = {}) {
  const {
    createRecorderFn = createRecorder,
    now = () => Date.now(),
    createObjectUrl = (blob: Blob) => URL.createObjectURL(blob),
    revokeObjectUrl = (uri: string) => URL.revokeObjectURL(uri),
  } = deps;

  const recorderRef = useRef<Recorder | null>(null);
  const startedAtRef = useRef(0);
  // ⚠️ 用 ref 而不是只靠 state：卸載時的 cleanup 讀得到的必須是最新值，而 cleanup
  // 拿到的 state 是它掛上去那一刻的快照。
  const previewUriRef = useRef<string | null>(null);

  const [status, setStatus] = useState<VoiceRecordingStatus>("idle");
  const [durationMs, setDurationMs] = useState(0);
  const [audio, setAudio] = useState<ArrayBuffer | null>(null);
  const [mimeType, setMimeType] = useState("");
  const [previewUri, setPreviewUri] = useState<string | null>(null);

  const dropPreview = useCallback(() => {
    if (previewUriRef.current !== null) {
      revokeObjectUrl(previewUriRef.current);
      previewUriRef.current = null;
      setPreviewUri(null);
    }
  }, [revokeObjectUrl]);

  const start = useCallback(async (): Promise<boolean> => {
    if (recorderRef.current !== null) {
      return false;
    }
    dropPreview();
    const recorder = createRecorderFn();
    const started = await recorder.start();
    if (!started) {
      // 麥克風拿不到：不進錄音狀態，讓呼叫端顯示白話說明。不擲例外——擲出去
      // 整個畫面會白掉，家屬連重試的按鈕都看不到（同 recorder.ts 的既有理由）。
      return false;
    }
    recorderRef.current = recorder;
    startedAtRef.current = now();
    setAudio(null);
    setMimeType("");
    setDurationMs(0);
    setStatus("recording");
    return true;
  }, [createRecorderFn, dropPreview, now]);

  const stop = useCallback(async (): Promise<void> => {
    const recorder = recorderRef.current;
    if (recorder === null) {
      return;
    }
    recorderRef.current = null;
    const bytes = await recorder.stop();
    // 長度用時間戳算，不是數 tick——tick 會漂，而漂掉的那零點幾秒正好落在門檻上。
    setDurationMs(now() - startedAtRef.current);
    setStatus("recorded");
    if (bytes === null || bytes.byteLength === 0) {
      // 錄到空的（軌道被系統搶走等）：當成沒錄到，`isLongEnough` 會擋住送出。
      setAudio(null);
      return;
    }
    const type = recorder.mimeType();
    setAudio(bytes);
    setMimeType(type);
    const uri = createObjectUrl(new Blob([bytes], { type }));
    previewUriRef.current = uri;
    setPreviewUri(uri);
  }, [createObjectUrl, now]);

  const reset = useCallback(() => {
    dropPreview();
    setAudio(null);
    setMimeType("");
    setDurationMs(0);
    setStatus("idle");
  }, [dropPreview]);

  // 錄音中的計時器。
  useEffect(() => {
    if (status !== "recording") {
      return;
    }
    const handle = setInterval(() => setDurationMs(now() - startedAtRef.current), TICK_MS);
    return () => clearInterval(handle);
  }, [status, now]);

  // ⚠️ 依賴陣列必須是空的，**不可以放 `revokeObjectUrl`**（2026-08-12 iPhone 實測修正）。
  //
  // `deps: VoiceRecordingDeps = {}` 是預設參數，每次呼叫都會重建，於是上面四個預設
  // 實作每次 render 都是新的函式實體。把 `revokeObjectUrl` 放進依賴陣列的話，這個
  // 「卸載時清理」的 effect 會在**每一次 render** 都跑一次 cleanup——錄音才剛開始，
  // 第一次重繪就把 `recorder.stop()` 呼叫掉、`recorderRef` 也清成 null。之後家屬按
  // 「停止」時 `stop()` 讀到 null 直接 return，畫面永遠停在錄音中、計時器一直跳。
  //
  // ⚠️ 為什麼測試沒抓到：本檔的測試都把 deps 物件建好一次重複使用，識別碼是穩定的，
  // 這個 effect 就不會重跑。正式路徑（`VoiceProfileScreen` 呼叫 `useVoiceRecording()`
  // 不帶參數）才會踩到。見 useVoiceRecording.test.ts「重繪不可以把正在進行的錄音停掉」。
  //
  // 清理本身的理由不變：錄音中被切走（家屬按返回、窄螢幕切頁籤）而沒有停掉錄音器的話，
  // 麥克風軌道沒有人關，分頁的錄音指示燈會一直亮著。blob 網址同理，不回收就一直佔著
  // 記憶體。這是 web 端同一類坑的第五次（前四次見 12 §Task 8 的記載）。
  // 「最新值」放 ref：讓上面那個 effect 的依賴陣列能保持空的，又不會清理到過期的網址。
  // 寫入放在 effect 裡而不是 render 期間——並行渲染下 render 必須無副作用
  // （eslint react-hooks/refs）。
  const revokeObjectUrlRef = useRef(revokeObjectUrl);
  useEffect(() => {
    revokeObjectUrlRef.current = revokeObjectUrl;
  }, [revokeObjectUrl]);
  useEffect(() => {
    return () => {
      void recorderRef.current?.stop();
      recorderRef.current = null;
      if (previewUriRef.current !== null) {
        revokeObjectUrlRef.current(previewUriRef.current);
        previewUriRef.current = null;
      }
    };
  }, []);

  return {
    status,
    durationMs,
    audio,
    mimeType,
    previewUri,
    isLongEnough: audio !== null && durationMs >= MIN_RECORDING_MS,
    start,
    stop,
    reset,
  };
}
