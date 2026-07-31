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
  return {
    uri: URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: "audio/mp4" })),
  };
}

export type WebPlayer = PlayerLike & {
  pause: () => void;
  dispose: () => void;
  /** 測試用。 */
  element: HTMLAudioElement;
};

export function createWebPlayer(): WebPlayer {
  const element = new Audio();
  // 長輩端不需要背景播放，也不要它預載——回覆是即時產生的。
  element.preload = "auto";
  let currentBlobUrl: string | null = null;

  function revokeCurrent() {
    if (currentBlobUrl !== null) {
      URL.revokeObjectURL(currentBlobUrl);
      currentBlobUrl = null;
    }
  }

  return {
    element,

    addListener(_event, listener) {
      const handler = () => listener({ didJustFinish: true });
      element.addEventListener("ended", handler);
      return { remove: () => element.removeEventListener("ended", handler) };
    },

    replace(source) {
      // 換下一則之前先回收上一則。只回收 blob:——分段續拉來的可能是 https 的
      // 簽章網址，那個回收不得（也不需要）。
      revokeCurrent();
      element.src = source.uri;
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
      element.removeAttribute("src");
    },
  };
}
