import { useState } from "react";

import { GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { apiErrorMessage, ApiError } from "@/api";

import { loginGuardian } from "./api";

export function LoginScreen(props: { onRegister: () => void; onDone: () => void }) {
  const { signIn } = GuardianSession.useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    setBusy(true);
    try {
      const session = await loginGuardian(email, password);
      signIn({ token: session.token, display_name: session.name });
      props.onDone();
    } catch (exc) {
      // ⚠️ 這裡的 401 是「帳密不對」，要顯示給人看，不可套用 signOutOnAuthError
      // 把人踢出去——他本來就還沒進來。
      if (exc instanceof ApiError && exc.status === 401) {
        setError(strings.guardianLogin.wrongCredentials);
      } else {
        // 其餘後端錯誤照實顯示後端那句話：它已經是繁中人話（D-24），比自己重寫
        // 一句準確——與 ElderDetailScreen／SchedulesScreen 同一個原則。
        //
        // ⚠️ 一律說成「連線失敗」會誤導：密碼欄留空按登入（前端沒擋）會讓後端的
        // `min_length=1` 觸發 422、回「輸入資料格式不正確」，而畫面說連線失敗，
        // 使用者於是去查網路、重按十次都一樣。真正連不上（fetch 自己擲的
        // TypeError，不是 ApiError）才留給 connectionFailed。
        //
        // ⚠️ apiErrorMessage 多擋一層：後端回應不是合法 JSON（隧道抖動的 502
        // HTML、未捕捉例外的 500 text/plain）時，exc.message 會是 shared/client.ts
        // 自造的英文字面值（如 `HTTP 502`），這裡一律退回 connectionFailed。
        setError(apiErrorMessage(exc, strings.common.connectionFailed));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 p-5">
      <h1 className="text-lg font-bold text-ink">{strings.guardianLogin.title}</h1>
      <Field
        label={strings.common.emailLabel}
        value={email}
        onChange={setEmail}
        type="email"
        autoComplete="email"
        placeholder={strings.common.emailPlaceholder}
      />
      <Field
        label={strings.common.passwordLabel}
        value={password}
        onChange={setPassword}
        type="password"
        autoComplete="current-password"
        placeholder={strings.common.passwordPlaceholder}
      />
      <ErrorText message={error} />
      <Button label={strings.common.login} onClick={submit} busy={busy} />
      <Button label={strings.guardianLogin.registerLink} onClick={props.onRegister} variant="outline" />
    </div>
  );
}
