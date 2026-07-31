/**
 * 長輩帳密登入（✅ D-71 己-6）：只管「重登」（換手機／登出後）。
 * 首次使用仍要掃家人給的 QR 完成配對——這一點在 403 的文案裡講清楚。
 */

import { useState } from "react";

import { apiErrorMessage, ApiError } from "@/api";
import { ElderSession } from "@/session/contexts";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";

import { loginElder } from "./api";

export function LoginScreen(props: { onDone: () => void }) {
  const { signIn } = ElderSession.useSession();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    setBusy(true);
    try {
      const session = await loginElder(phone, password);
      signIn({ token: session.token, display_name: session.name });
      props.onDone();
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 403) {
        // 403＝還沒配對過。這與「密碼打錯」是完全不同的兩件事，講錯會讓長輩
        // 一直重打密碼。
        setError(strings.elderLogin.notPaired);
      } else if (exc instanceof ApiError && exc.status === 401) {
        setError(strings.elderLogin.wrongCredentials);
      } else {
        // ⚠️ 審查發現：一律說成「連線失敗」會誤導。手機號碼欄空白或太短（如
        // 只打了「09」）會讓後端 `ElderLoginIn.phone: Field(min_length=8)`
        // 觸發 422 `validation_error`，回「輸入資料格式不正確」——這句話已
        // 是繁中人話（D-24），直接顯示比「連線失敗」準確：講「連線失敗」的
        // 話，長輩會去確認 Wi-Fi、反覆重試，永遠不會想到是欄位沒填好。
        // `guardian/LoginScreen.tsx` 已修過同一類問題（見該檔註解），此處
        // 補齊同一套原則。`apiErrorMessage` 多擋一層：後端回應不是合法 JSON
        // 時 exc.message 會是 shared/client.ts 自造的英文字面值，一律退回
        // connectionFailed。
        setError(apiErrorMessage(exc, strings.common.connectionFailed));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col justify-center gap-5 p-6">
      <p className="text-elder-min leading-relaxed text-ink-soft">{strings.elderLogin.hint}</p>
      <Field
        label={strings.elderLogin.phoneLabel}
        value={phone}
        onChange={setPhone}
        type="tel"
        size="big"
        // ⚠️ 審查發現：這裡原本寫死 "09xxxxxxxx"，但 strings.ts 已有同值的
        // elderDetail.accountPhonePlaceholder（家屬代辦長輩帳密畫面用同一種
        // 手機號碼格式提示）——兩處各自寫死同一個字面值，日後改格式（如
        // 加國碼）只改一處會漂。重用既有鍵，不新增第二個同義字串。
        placeholder={strings.elderDetail.accountPhonePlaceholder}
      />
      <Field
        label={strings.common.passwordLabel}
        value={password}
        onChange={setPassword}
        type="password"
        size="big"
        autoComplete="current-password"
      />
      <ErrorText message={error} size="big" />
      <Button label={strings.common.login} size="big" onClick={submit} busy={busy} />
    </div>
  );
}
