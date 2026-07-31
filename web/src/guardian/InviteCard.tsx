/**
 * 綁定碼卡片：碼、QR 圖、複製、以及「送到長輩的手機」。
 *
 * ⚠️ 「送到長輩的手機」是刻意加的內測捷徑（spec W-15 附記）：在同一個瀏覽器頁面
 * 裡，要用一欄的相機去掃另一欄螢幕上的 QR 實務上很蠢。真實掃碼路徑完整保留，
 * 實機展示或用手機開這個網址時仍然走那條。
 *
 * ⚠️ `onSendToElder` 由呼叫端（`HomeScreen`／`ElderDetailScreen`）決定要不要傳：
 * 傳了才畫這顆鈕，接線一路上到 `stage/StagePage.tsx`（見該檔與 `elder/ElderApp.tsx`
 * 對 `prefilledCode` 的說明，P4 Task 3）。獨立測試這支畫面（不透過 `StagePage`）
 * 時沒有另一欄可以送，不傳的話這顆鈕不該出現。
 */

import QRCode from "qrcode";
import { useEffect, useState } from "react";

import { strings } from "@/strings";
import { Button } from "@/ui/Button";

export function InviteCard(props: { code: string; onSendToElder?: () => void }) {
  const { code, onSendToElder } = props;
  const [dataUrl, setDataUrl] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    // QR 產生是非同步的；產不出來就只是沒有圖，綁定碼本身照樣可以用手打。
    QRCode.toDataURL(code, { width: 200, margin: 1 })
      .then((url) => {
        if (alive) setDataUrl(url);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [code]);

  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl bg-background p-4">
      <p className="self-start text-sm text-ink-soft">{strings.guardianHome.inviteHint}</p>
      <p className="text-2xl font-extrabold tracking-widest text-primary">{code}</p>
      {dataUrl ? (
        <img src={dataUrl} alt={strings.guardianHome.qrAlt} className="rounded-xl bg-white p-2" />
      ) : null}
      <Button
        label={copied ? strings.guardianHome.copied : strings.guardianHome.copyCode}
        variant="outline"
        onClick={() => {
          // ⚠️ 只在**成功**時才切成「已複製」。剪貼簿在非安全來源與部分瀏覽器會
          // 失敗，而那正是這段程式碼要處理的情形——失敗卻顯示「已複製」，家屬就
          // 不會想去手抄，但剪貼簿上什麼都沒有。仍然不跳錯誤對話框：碼本來就顯示
          // 在畫面上，人可以自己抄，為此嚇他一跳不划算。
          navigator.clipboard
            ?.writeText(code)
            .then(() => setCopied(true))
            .catch(() => undefined);
        }}
      />
      {onSendToElder ? (
        <Button label={strings.guardianHome.sendToElder} variant="outline" onClick={onSendToElder} />
      ) : null}
    </div>
  );
}
