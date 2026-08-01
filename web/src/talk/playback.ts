/**
 * 網頁播放（取代 App 的 expo-audio ＋ expo-file-system）。
 *
 * ⚠️ App 版把 WebSocket 直送的位元組寫成 cache 目錄的 .m4a 檔；`expo-file-system`
 * 在網頁是空實作（只印一行 warning），所以這裡改成 blob URL。介面刻意與 App 版
 * 相同（`writeReplyAudio(bytes) → { uri }`），搬過來的 `talkSocket` 一行都不必動。
 *
 * ⚠️ blob URL **必須回收**。不回收的話每一輪漏一個，一場展示下來會累積幾十 MB
 * 在記憶體裡——而瀏覽器不會替你清，它不知道你不再需要它了。
 */

import type { PlayerLike } from "./talkSocket";

/**
 * iOS 音訊解鎖用的無聲音檔路徑，與 `audioUnlock.ts` 共用同一個值（該檔案自
 * 本模組匯入，不各自定義一份、避免兩處的字面值日後漂移）。`createWebPlayer`
 * 需要知道這個值，理由見 `addListener` 內的說明。
 */
export const UNLOCK_AUDIO_URI = "/demo/silent.wav";

/**
 * 尚未被回收的 blob URL（`writeReplyAudio` 建立、但還沒被 `replace()`／
 * `dispose()` 回收掉）。給 `revokeQueuedReplyAudio` 用。
 */
const pendingBlobUrls = new Set<string>();

/** 與 App 版同名同介面：回可以直接餵給播放器的 uri。 */
export function writeReplyAudio(bytes: Uint8Array): { uri: string } {
  if (bytes.byteLength === 0) {
    // 空音檔餵給播放器只會靜默失敗，而那一輪的字幕還是會顯示——長輩看得到字、
    // 等不到聲音，也不知道發生了什麼。擲出去讓呼叫端明確丟掉這一則。
    throw new Error("回覆音檔是空的");
  }
  // 型別用 audio/mp4：後端送的是 AAC/m4a。瀏覽器靠這個決定用哪個解碼器。
  //
  // ⚠️ 修正 brief 原始版本的編譯錯誤：`bytes` 的型別是不帶泛型參數的 `Uint8Array`
  // （即 `Uint8Array<ArrayBufferLike>`，底層緩衝區可能是 `SharedArrayBuffer`），
  // 但 TypeScript 5.9 的 DOM 型別將 `Blob` 建構子收窄為只吃
  // `ArrayBufferView<ArrayBuffer>`——兩者不相容，`tsc --noEmit` 會報 TS2322。
  // `new Uint8Array(bytes)` 走的是「從 `ArrayLike<number>` 複製一份」多載，
  // 保證回傳 `Uint8Array<ArrayBuffer>`；位元組量通常僅數十 KB，多複製一次可忽略。
  const uri = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: "audio/mp4" }));
  pendingBlobUrls.add(uri);
  return { uri };
}

/**
 * 回收所有尚未播到、卻已經造出來的 blob URL（例如長輩插嘴、播放佇列被
 * `clear()` 清空時，裡面還沒輪到 `replace()` 的那幾則）。
 *
 * ⚠️ **為什麼不讓 `talkSocket.ts::createPlaybackQueue` 的 `clear()` 自己
 * 回收**：那支佇列刻意是「純資料結構」（見該檔案 docstring），完全不知道
 * `PlaybackItem.audioUrl` 在網頁端可能是需要回收的 blob URL——把回收邏輯
 * 塞進去會讓一支通用 FIFO 佇列耦合到「播放媒介剛好是網頁 blob URL」這個
 * web 端專屬細節；App 端同一支佇列用的是本地檔路徑，完全不需要這件事。
 * 改把回收能力放在本模組，由呼叫端（接線佇列的任務）在 `queue.clear()`
 * 的**同時**呼叫這支函式，並傳入目前正在播放中的 uri（若有）以免連正在
 * 播的那一則都被回收掉。
 *
 * ⚠️ **Task 4 記載的「尚未接線」缺口已於 P3 Task 8 收斂**，目前有三個呼叫端：
 * `elder/useTalk.ts::startRecording`（`playQueue.clear()` 的同一處）、同檔播放
 * 佇列丟棄「收音期間抵達的那一則」時，以及 effect cleanup（切頁籤／卸載／換
 * token，不帶例外、全掃）。
 */
export function revokeQueuedReplyAudio(exceptUri?: string): void {
  for (const uri of pendingBlobUrls) {
    if (uri !== exceptUri) {
      URL.revokeObjectURL(uri);
      pendingBlobUrls.delete(uri);
    }
  }
}

/**
 * 回收**單獨一則**已落地、確定不會再播的回覆音檔。
 *
 * ⚠️ 為什麼不能用 `revokeQueuedReplyAudio` 代替：那一支是「除了這一則以外全部
 * 回收」，只留得住一個例外。長輩插嘴之後暫存下來等補播的（見 `elder/useTalk.ts`
 * 的 `deferredTurnsRef`）不只是複數則、還是複數**輪**——2026-08-01 續段直送引入
 * 之後，一輪的常態是 ack＋reply＋多個續段共四則以上（不再是原本「一輪最多兩則」
 * 的假設），所以「不能一次回收多個例外」這個理由比原本更強：擠掉最舊的一輪時，
 * 呼叫端得逐一針對該輪的**每一則**呼叫這支函式，若改用「除了這一則以外全部
 * 回收」的 `revokeQueuedReplyAudio`，會把還要補播的那幾輪、每輪好幾則全部一起
 * 毀掉——症狀是補播時播放器拿到一個已經失效的 blob URL，靜靜地沒有聲音。這裡
 * 只針對指定的那一則，能不能整輪回收乾淨要靠呼叫端逐則呼叫。
 *
 * ⚠️ **以「在不在集合裡」為唯一判準**，不另外檢查 `blob:` 前綴：集合只裝
 * `writeReplyAudio` 造出來的 blob URL，分段續拉來的 https 簽章網址本來就不在裡面
 * ——多寫一道前綴守門是恆真的判斷（實測變異：拿掉它 65 條全綠）。同一則被回收兩次
 * （補播佇列擠掉一則、之後 cleanup 又全掃一次）也因此自然是 no-op。
 */
export function revokeReplyAudio(uri: string): void {
  if (pendingBlobUrls.delete(uri)) {
    URL.revokeObjectURL(uri);
  }
}

/** 測試用：清空 `writeReplyAudio` 的內部追蹤狀態，避免測試之間互相汙染。 */
export function resetPendingReplyAudioForTest(): void {
  pendingBlobUrls.clear();
}

export type WebPlayer = PlayerLike & {
  pause: () => void;
  dispose: () => void;
  /** 測試用。 */
  element: HTMLAudioElement;
};

export function createWebPlayer(): WebPlayer {
  const element = new Audio();
  // 長輩端不需要背景播放；預載設 auto——讓瀏覽器在 replace() 指定 src 後盡快
  // 開始緩衝，播放鍵按下去不必再等一輪緩衝。
  element.preload = "auto";
  let currentBlobUrl: string | null = null;
  // iOS 解鎖用的無聲檔目前是不是這顆播放器正載入的來源——見 addListener。
  let isUnlockClip = false;

  function revokeCurrent() {
    if (currentBlobUrl !== null) {
      URL.revokeObjectURL(currentBlobUrl);
      pendingBlobUrls.delete(currentBlobUrl);
      currentBlobUrl = null;
    }
  }

  return {
    element,

    addListener(_event, listener) {
      const handler = () => {
        // ⚠️ iOS 解鎖用的無聲檔播完不算「一則回覆播完了」：這顆播放器是
        // `unlockAudio` 刻意共用的同一顆（iOS 的解鎖綁在單一
        // `HTMLMediaElement` 上，換一顆播放器等於沒解鎖）。若不濾掉，長輩
        // 第一次按下麥克風時，這段約 50ms 無聲檔播完發出的 `ended` 會被
        // 常駐監聽者當成「一則回覆播完了」→ 佇列是空的 → 提前把畫面切回
        // 待機——而長輩其實還在講話。只在「目前載入的就是解鎖用無聲檔」
        // 時濾掉，下一次 `replace()` 換成真的回覆後自動恢復正常通知。
        if (isUnlockClip) return;
        listener({ didJustFinish: true });
      };
      element.addEventListener("ended", handler);
      return { remove: () => element.removeEventListener("ended", handler) };
    },

    replace(source) {
      // 換下一則之前先回收上一則。只回收 blob:——分段續拉來的可能是 https 的
      // 簽章網址，那個回收不得（也不需要）。
      revokeCurrent();
      element.src = source.uri;
      isUnlockClip = source.uri === UNLOCK_AUDIO_URI;
      if (source.uri.startsWith("blob:")) {
        currentBlobUrl = source.uri;
      }
    },

    play() {
      // play() 回的 promise 在被瀏覽器擋下時會 reject（iOS 未解鎖、分頁在背景）。
      // 不 catch 會噴一個沒有人處理的 rejection，而那對長輩沒有任何意義。
      void element.play().catch(() => undefined);
    },

    pause() {
      element.pause();
    },

    dispose() {
      element.pause();
      revokeCurrent();
      // 離開對講機畫面時徹底清乾淨：連還沒播到、佇列裡剩下的 blob URL 也
      // 一併回收（沒有例外 uri——這顆播放器本身都要丟棄了）。
      revokeQueuedReplyAudio();
      element.removeAttribute("src");
      // `removeAttribute("src")` 只清掉屬性，元素本身可能還抓著已載入的
      // 資源；接一次 load() 才是標準的完整釋放慣用法。
      element.load();
    },
  };
}
