/**
 * 把 WebSocket 推下來的回覆音檔位元組落地成可播放的本地檔（2026-07-30 延遲優化 C1）。
 *
 * ## 為什麼需要落地
 *
 * `expo-audio` 的 `AudioSource` 只吃 uri／assetId，**沒有任何吃記憶體位元組的路**
 * （見 `expo-audio/build/Audio.types.d.ts`）。iOS 其實認得 `data:audio/…` 這種
 * base64 uri，但它的原生實作就是「解 base64 → 寫進 `temporaryDirectory` → 用 UUID
 * 當檔名」，而那個檔名我們拿不到、它也永不刪除——等於每播一次漏一個暫存檔，比自己
 * 寫檔更糟；副檔名還是靠 MIME 推導（`audio/m4a` 是非標準 MIME，推不出來會變 `.dat`，
 * 而 AVPlayer 對推不出型別的檔會直接載不起來）。自己寫檔成本一樣、風險全消。
 *
 * ## 為什麼獨立成一個模組
 *
 * `talkSocket.ts` 的 docstring 明講它「刻意不碰音訊播放與 React，所以可以完全離線
 * 單元測試」，而 `talkSocket.test.ts` 確實不 import 任何 expo 模組。把
 * `expo-file-system` 塞進那裡會直接毀掉那份測試的前提，故本模組獨立，並由
 * `talk.tsx` 以注入點的形式交給 socket（同 `createSocket`／`setTimeoutFn` 的既有慣例）。
 */

import { Directory, File, Paths } from "expo-file-system";

/** `expo-audio` 的 `AudioSource` 子集：本模組只產出 `{ uri }`。 */
export type ReplyAudioSource = { uri: string };

const REPLY_DIR_NAME = "kinsun-reply";

/**
 * 環狀保留幾個檔。
 *
 * ⚠️ 刻意**不做「播完就刪」**：`playAndWait` 的保險逾時可能在播放器還在讀檔的時候
 * 就放行（事件沒來的那種情形），而一輪最多同時有兩則在飛（安撫話、答案）。留 3 個
 * 保證「正在播的那一個」永遠不在刪除範圍內——這樣就完全不必去賭「unlink 一個正在
 * 播的檔會怎樣」這件事。
 */
const KEEP_FILES = 3;

let counter = 0;

function ensureDir(): Directory {
  const dir = new Directory(Paths.cache, REPLY_DIR_NAME);
  dir.create({ intermediates: true, idempotent: true });
  return dir;
}

function trim(dir: Directory): void {
  try {
    const files = dir
      .list()
      .filter((entry): entry is File => entry instanceof File)
      // 檔名前綴是零填補的遞增序號，所以字典序＝建立順序。
      .sort((a, b) => (a.name < b.name ? -1 : 1));
    for (const stale of files.slice(0, Math.max(0, files.length - KEEP_FILES))) {
      try {
        stale.delete();
      } catch {
        // 刪不掉（可能正在播）就跳過，下一輪再試；上限由 cache 目錄的系統回收兜底。
      }
    }
  } catch {
    // 列目錄失敗絕不可讓這一輪的回覆播不出來——長輩會以為金孫沒回答。
  }
}

/**
 * 進對講機畫面時呼叫：清掉上一次 session 的殘留。
 *
 * cache 目錄只在「裝置儲存吃緊」時才被系統回收，不會每輪幫我們清，故自己收。
 */
export function purgeReplyAudio(): void {
  try {
    const dir = new Directory(Paths.cache, REPLY_DIR_NAME);
    if (dir.exists) {
      dir.delete();
    }
  } catch {
    // 清不掉不影響播放。
  }
}

/**
 * 把音檔位元組寫成本地檔，回傳可直接餵給 `player.replace()` 的 uri。
 *
 * ⚠️ 副檔名必須是 `.m4a`：iOS 的 AVPlayer 推不出型別就載不起來（`expo-audio` 自己的
 * `resolveSource.js` 註解就寫著這件事）。
 *
 * ⚠️ `File.write` 是**同步**的原生呼叫，回傳時檔案已完整落盤，所以
 * write → replace → play 之間沒有競態。20～100KB 落地在毫秒級。
 *
 * 寫失敗直接拋：呼叫端（`talkSocket` 的 binary frame 處理）會接住並丟掉這一則，
 * 播放佇列本來就逐則 catch，不會整條卡死。
 */
export function writeReplyAudio(bytes: Uint8Array): ReplyAudioSource {
  if (bytes.byteLength === 0) {
    throw new Error("回覆音檔是空的");
  }
  const dir = ensureDir();
  counter += 1;
  const name = `${String(counter).padStart(6, "0")}-${Date.now()}.m4a`;
  const file = new File(dir, name);
  file.write(bytes);
  trim(dir);
  return { uri: file.uri };
}
