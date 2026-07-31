/**
 * 長輩帳密登入（✅ D-71 己-6）：只管「重登」（換手機／登出後）。
 * 首次使用仍要掃家人給的 QR 完成配對——這一點在 403 的文案裡講清楚。
 */

import { useState } from "react";

import { ApiError } from "@/api";
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
        setError(strings.common.connectionFailed);
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
        placeholder="09xxxxxxxx"
      />
      <Field
        label={strings.common.passwordLabel}
        value={password}
        onChange={setPassword}
        type="password"
        size="big"
        autoComplete="current-password"
      />
      <ErrorText message={error} />
      <Button label={strings.common.login} size="big" onClick={submit} busy={busy} />
    </div>
  );
}
