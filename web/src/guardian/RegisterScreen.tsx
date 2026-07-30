import { useState } from "react";

import { ApiError } from "@/api";
import { GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";

import { registerGuardian } from "./api";

/** 密碼下限與後端的 password_too_short 一致；前端先擋是為了少一趟往返。 */
const MIN_PASSWORD_LENGTH = 8;

export function RegisterScreen(props: { onLogin: () => void; onDone: () => void }) {
  const { signIn } = GuardianSession.useSession();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(strings.guardianRegister.passwordTooShort);
      return;
    }
    setBusy(true);
    try {
      const session = await registerGuardian(email, password, name.trim());
      signIn({ token: session.token, display_name: session.name });
      props.onDone();
    } catch (exc) {
      setError(
        exc instanceof ApiError && exc.code === "email_taken"
          ? strings.guardianRegister.emailTaken
          : strings.common.connectionFailed,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 p-5">
      <h1 className="text-lg font-bold text-ink">{strings.guardianRegister.title}</h1>
      <Field
        label={strings.guardianRegister.nameLabel}
        value={name}
        onChange={setName}
        placeholder={strings.guardianRegister.namePlaceholder}
      />
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
        autoComplete="new-password"
        placeholder={strings.common.passwordPlaceholder}
      />
      <ErrorText message={error} />
      <Button label={strings.guardianRegister.submit} onClick={submit} busy={busy} />
      <Button label={strings.guardianRegister.loginLink} onClick={props.onLogin} variant="outline" />
    </div>
  );
}
