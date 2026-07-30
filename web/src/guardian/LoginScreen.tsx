import { useState } from "react";

import { GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { ApiError } from "@/api";

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
      setError(
        exc instanceof ApiError && exc.status === 401
          ? strings.guardianLogin.wrongCredentials
          : strings.common.connectionFailed,
      );
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
