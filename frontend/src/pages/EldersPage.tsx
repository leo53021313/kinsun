import { useEffect, useState } from "react";
import { Link } from "react-router";

import { type Elder, createElder, generateGuardianInvite, listElders } from "../api";
import { strings } from "../strings";

type CodeNotice = { kind: "elder" | "guardian"; code: string };

export function EldersPage() {
  const [elders, setElders] = useState<Elder[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [notice, setNotice] = useState<CodeNotice | null>(null);

  function reload() {
    listElders()
      .then(setElders)
      .catch(() => setError(strings.common.loadFailed));
  }

  useEffect(reload, []);

  async function create() {
    setError(null);
    if (!newName.trim()) {
      setError(strings.elders.nameRequired);
      return;
    }
    try {
      // 家屬名改由後端從 ID token 取 LINE 顯示名稱（✅ 庚-29），前端不再自送。
      const res = await createElder(newName.trim());
      setNewName("");
      setNotice({ kind: "elder", code: res.invite_code });
      reload();
    } catch {
      setError(strings.elders.createFailed);
    }
  }

  async function invite(elderId: string) {
    setError(null);
    try {
      const res = await generateGuardianInvite(elderId);
      setNotice({ kind: "guardian", code: res.invite_code });
    } catch {
      setError(strings.elders.inviteFailed);
    }
  }

  if (!elders) return <p>{strings.common.loading}</p>;
  return (
    <main>
      <h1>{strings.elders.title}</h1>
      {error && <p>{error}</p>}
      {notice && (
        <p>
          {notice.kind === "elder"
            ? strings.elders.elderCodeNotice
            : strings.elders.guardianCodeNotice}
          <strong>{notice.code}</strong>
        </p>
      )}
      <ul>
        {elders.map((e) => (
          <li key={e.elder_id}>
            {e.name}：
            <Link to={`/elders/${e.elder_id}/schedules`}>{strings.elders.linkSchedules}</Link>
            {" / "}
            {" / "}
            <Link to={`/elders/${e.elder_id}/health-report`}>{strings.elders.linkHealthReport}</Link>
            {" / "}
            <button type="button" onClick={() => invite(e.elder_id)}>
              {strings.elders.inviteGuardian}
            </button>
          </li>
        ))}
      </ul>
      <h2>{strings.elders.addHeading}</h2>
      <input
        value={newName}
        onChange={(e) => setNewName(e.target.value)}
        placeholder={strings.elders.namePlaceholder}
      />
      <button type="button" onClick={create}>
        {strings.elders.createButton}
      </button>
    </main>
  );
}
