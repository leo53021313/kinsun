import { useEffect, useMemo, useState } from "react";

import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { Section } from "@/ui/Section";
import type { Elder } from "kinsun-shared/types";

import { createElder, listElders, logoutGuardian } from "./api";
import { InviteCard } from "./InviteCard";

export function HomeScreen(props: {
  onOpenElder: (elderId: string, elderName: string) => void;
  onOpenNotifications: () => void;
}) {
  const { session, signOut } = GuardianSession.useSession();
  const token = session?.token ?? "";
  const [elders, setElders] = useState<Elder[]>([]);
  const [newName, setNewName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // makeSignOutOnAuthError 是工廠、回傳的是函式值，所以用 useMemo 而非 useCallback
  // （useCallback 收的應該是行內函式表達式，react-hooks 規則會擋）。signOut 在
  // session 工廠裡是 useCallback([]) 的穩定參考，所以這個值也穩定，不會讓下面的
  // effect 反覆重打 API。
  const signOutOn401 = useMemo(() => makeSignOutOnAuthError(signOut), [signOut]);

  useEffect(() => {
    if (!token) {
      return;
    }
    let alive = true;
    listElders(token)
      .then((list) => {
        if (alive) setElders(list);
      })
      .catch((exc) => {
        if (signOutOn401(exc)) return;
        if (alive) setError(strings.common.loadFailed);
      });
    return () => {
      alive = false;
    };
  }, [token, signOutOn401]);

  async function addElder() {
    const name = newName.trim();
    if (!name) {
      setError(strings.guardianHome.nameRequired);
      return;
    }
    setError("");
    setBusy(true);
    try {
      const created = await createElder(name, token);
      // ⚠️ 帶上 nickname：後端一直都有回它，App 版曾經在這裡把它丟掉，於是剛新增
      // 的那一筆在列表上少一個稱謂、要重新整理才會出現（A-10）。
      setElders((prev) => [
        ...prev,
        { elder_id: created.elder_id, name: created.name, nickname: created.nickname },
      ]);
      setInviteCode(created.invite_code);
      setNewName("");
    } catch (exc) {
      if (signOutOn401(exc)) return;
      setError(strings.guardianHome.addFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-ink">{strings.guardianHome.title}</h1>
        <button
          type="button"
          onClick={props.onOpenNotifications}
          className="min-h-12 rounded-xl border border-line bg-surface px-4 text-sm font-semibold text-ink"
        >
          {strings.guardianHome.notify}
        </button>
      </div>

      <Section title={strings.guardianHome.addElderSection}>
        <Field
          label={strings.guardianHome.elderNameLabel}
          value={newName}
          onChange={setNewName}
          placeholder={strings.guardianHome.elderNamePlaceholder}
        />
        <p className="text-xs leading-5 text-ink-soft">{strings.guardianHome.consent}</p>
        <Button label={strings.guardianHome.createElder} onClick={addElder} busy={busy} />
        {inviteCode ? <InviteCard code={inviteCode} /> : null}
        <ErrorText message={error} />
      </Section>

      {elders.length === 0 ? (
        <EmptyHint text={strings.guardianHome.empty} />
      ) : (
        <ul className="flex flex-col gap-2">
          {elders.map((elder) => (
            <li key={elder.elder_id}>
              <button
                type="button"
                onClick={() => props.onOpenElder(elder.elder_id, elder.name)}
                className="flex min-h-14 w-full items-center justify-between rounded-2xl border border-line bg-surface px-4 text-left"
              >
                <span className="text-base font-bold text-ink">{elder.name}</span>
                <span aria-hidden className="text-xl text-ink-soft">
                  ›
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <Button
        label={strings.guardianHome.logout}
        variant="outline"
        onClick={async () => {
          await logoutGuardian(token).catch(() => undefined);
          signOut();
        }}
      />
    </div>
  );
}
