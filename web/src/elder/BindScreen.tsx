/**
 * 長輩配對：掃家人給的 QR（✅ D-54 丁-3）或輸入綁定碼，一次就好。
 *
 * ⚠️ 相機權限在**按下「掃描」時**才要，不是進畫面就要。長輩多半用手打，
 * 一進來就跳權限對話框只會嚇到他。
 */

import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/api";
import { ElderSession } from "@/session/contexts";
import { strings } from "@/strings";
import { createQrScanner, type QrScannerError } from "@/talk/qrScanner";
import { Button } from "@/ui/Button";
import { ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";

import { bindElderDevice } from "./api";

/**
 * 綁定失敗的五種情形，各給一句長輩能照做的話。
 *
 * ⚠️「invite_expired」對他沒有任何意義。每一種失敗都必須告訴他**下一步做什麼**
 * ——而下一步幾乎都是「請家人重新產生一組」。
 *
 * ⚠️ `invite_wrong_role`（409）：家屬把**自己的**邀請碼給長輩掃／打時會走到
 * 這裡，與「查無此碼」「已過期」是完全不同的原因——混在一起講，長輩會拿著同
 * 一組本來就不是給他用的碼反覆重試。
 */
const BIND_ERRORS: Record<string, string> = {
  invite_not_found: strings.elderBind.inviteNotFound,
  invite_used: strings.elderBind.inviteUsed,
  invite_expired: strings.elderBind.inviteExpired,
  too_many_attempts: strings.elderBind.tooManyAttempts,
  invite_wrong_role: strings.elderBind.inviteWrongRole,
};

/**
 * `QrScannerError` 有六種（見 `talk/qrScanner.ts`），不是兩種——每一種都要有
 * 對應的長輩話、且都要講「下一步做什麼」（多半是「直接輸入號碼」）。
 */
const SCANNER_ERRORS: Record<QrScannerError, string> = {
  denied: strings.elderBind.cameraPermission,
  unsupported: strings.elderBind.cameraUnsupported,
  "not-found": strings.elderBind.cameraNotFound,
  "in-use": strings.elderBind.cameraInUse,
  "insecure-origin": strings.elderBind.cameraInsecureOrigin,
  "no-signal": strings.elderBind.cameraNoSignal,
};

export function BindScreen(props: {
  prefilledCode?: string;
  /**
   * 「他是被登出才回到這個畫面的」要講的那句話（見 `ElderApp` 的 `signedOutNotice`）。
   *
   * ⚠️ 用來當**錯誤欄位的初始值**而不是另外畫一段：兩段同時掛著的話，長輩會同時
   * 看到「家人幫您重新設定了…」與「找不到這組號碼…」兩句紅字，不知道該信哪一句。
   * 當成初始值的話，他一送出就被這一次的結果取代，正好是我們要的。
   * ⚠️ 只在**掛載時**讀一次：這個畫面是被登出時才重新掛上來的（`ElderApp` 的路由
   * 從對講機換成配對，元件整個換掉），不會有「掛著不動、值卻換了」的情形。
   */
  signedOutNotice?: string;
  /**
   * 這一欄目前是否真的看得見（雙欄舞台在窄螢幕是頁籤擇一顯示，見
   * `stage/StagePage.tsx`）。⚠️ **不是**用來卸載這個畫面——卸載會丟掉長輩
   * 打到一半的號碼；只用來在「切走時」讓下面的相機 effect 停止，「切回來時」
   * 自動恢復（`scanning` 這個 state 本身完全不受影響）。預設 `true`：獨立
   * 渲染（如 `bind.test.tsx` 直接掛 `<ElderApp />`）時視為永遠看得見。
   */
  visible?: boolean;
  onDone: () => void;
  onLogin: () => void;
}) {
  const { visible = true } = props;
  const { signIn } = ElderSession.useSession();
  const [code, setCode] = useState(props.prefilledCode ?? "");
  const [error, setError] = useState(props.signedOutNotice ?? "");
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  async function submit(raw: string) {
    const trimmed = raw.trim();
    if (!trimmed) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      const session = await bindElderDevice(trimmed);
      signIn({ token: session.token, display_name: session.name });
      props.onDone();
    } catch (exc) {
      setError(
        exc instanceof ApiError && BIND_ERRORS[exc.code]
          ? BIND_ERRORS[exc.code]
          : strings.elderBind.bindFailed,
      );
    } finally {
      setBusy(false);
    }
  }

  // ⚠️ 相機資源要在每一條離開這個畫面狀態的路徑都釋放（見下方 return 的
  // cleanup）：掃到（onCode 內 setScanning(false)）、掃碼出錯（onError 內
  // setScanning(false)）、按「改用輸入號碼」取消、整個元件被卸載，以及
  // **這一欄被切到背景**（`visible` 變 `false`，見下）——這五條路徑最終都
  // 會讓這個 effect 的 cleanup 被呼叫到，`scanner.stop()` 保證相機軌道被
  // 關掉，指示燈不會留著。
  //
  // ⚠️ **審查發現的 Critical**：雙欄舞台在窄螢幕是頁籤擇一顯示
  // （`stage/StagePage.tsx`），非活動欄用 CSS `hidden` 隱藏、元件仍掛著
  // ——`MediaStream` 軌道與 `display:none` 無關，繼續存活。長輩按「掃描
  // QR 碼」後若切到家屬端頁籤，相機會一直開著直到整個分頁關閉。修法**不是**
  // 卸載非活動欄（會丟掉長輩打到一半的號碼），而是把「這一欄現在看得到嗎」
  // 當成 effect 的相依之一：`visible` 變 `false` 時，即使 `scanning` 仍是
  // `true`，也不建立新的 scanner；而上一輪 effect 的 cleanup（關掉舊的
  // scanner）一定會先跑，相機因此確實關閉。切回來、`visible` 再變 `true`
  // 時，只要 `scanning` 還是 `true`，effect 會重新建立 scanner、重新要求
  // 鏡頭（權限已授予，瀏覽器不會再跳一次對話框），畫面自動恢復。
  useEffect(() => {
    if (!scanning || !visible || videoRef.current === null) {
      return;
    }
    const scanner = createQrScanner({
      video: videoRef.current,
      onCode: (text) => {
        // 掃到就收工：同一個碼在連續幾幀都會被讀到，掃描器已經只回報第一次，
        // 這裡再關掉相機，避免它在送出期間繼續跑。
        setScanning(false);
        setCode(text.trim());
        void submit(text);
      },
      onError: (reason) => {
        setScanning(false);
        setError(SCANNER_ERRORS[reason]);
      },
    });
    return () => scanner.stop();
    // submit 只讀 state 與常數，不列入相依以免每次輸入都重開相機。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanning, visible]);

  if (scanning) {
    return (
      <div className="flex h-full flex-col gap-4 p-5">
        <p className="text-center text-elder-min text-ink">{strings.elderBind.scanHint}</p>
        {/* playsInline：iOS Safari 不加會把影片切成全螢幕播放器，掃碼畫面整個跑掉。 */}
        <video
          ref={videoRef}
          muted
          playsInline
          className="min-h-0 flex-1 rounded-2xl bg-ink object-cover"
        />
        <Button
          label={strings.elderBind.switchToManual}
          variant="outline"
          size="big"
          onClick={() => setScanning(false)}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col justify-center gap-5 p-6">
      <p className="text-center text-elder-min text-ink">{strings.elderBind.hint}</p>
      {props.prefilledCode ? (
        <p className="text-center text-elder-min text-success">
          {strings.elderBind.receivedFromGuardian}
        </p>
      ) : null}
      <Button
        label={strings.elderBind.scanQr}
        size="big"
        onClick={() => {
          setError("");
          setScanning(true);
        }}
        disabled={busy}
      />
      <Field
        label={strings.elderBind.codeLabel}
        value={code}
        onChange={setCode}
        size="big"
        placeholder={strings.elderBind.codePlaceholder}
      />
      <ErrorText message={error} size="big" />
      <Button
        label={strings.elderBind.start}
        size="big"
        onClick={() => void submit(code)}
        busy={busy}
        disabled={!code.trim()}
      />
      {/* ⚠️ 適老化：長輩端可點擊目標一律 ≥56px，這顆次要導覽按鈕也不例外
          （`size="big"` 對應 `Button` 的 64px，brief 原始版本漏了這個尺寸，
          僅預設的 48px「一般」尺寸，低於長輩端下限）。 */}
      <Button
        label={strings.elderBind.loginLink}
        variant="outline"
        size="big"
        onClick={props.onLogin}
        disabled={busy}
      />
    </div>
  );
}
