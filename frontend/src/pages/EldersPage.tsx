import liff from "@line/liff";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { type Elder, createElder, generateGuardianInvite, listElders } from "../api";

type CodeNotice = { kind: "elder" | "guardian"; code: string };

export function EldersPage() {
  const [elders, setElders] = useState<Elder[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [notice, setNotice] = useState<CodeNotice | null>(null);

  function reload() {
    listElders()
      .then(setElders)
      .catch(() => setError("載入失敗，請稍後再試"));
  }

  useEffect(reload, []);

  async function create() {
    setError(null);
    if (!newName.trim()) {
      setError("請輸入長輩稱呼");
      return;
    }
    try {
      const profile = await liff.getProfile();
      const res = await createElder(newName.trim(), profile.displayName);
      setNewName("");
      setNotice({ kind: "elder", code: res.invite_code });
      reload();
    } catch {
      setError("建立失敗，請稍後再試");
    }
  }

  async function invite(elderId: string) {
    setError(null);
    try {
      const res = await generateGuardianInvite(elderId);
      setNotice({ kind: "guardian", code: res.invite_code });
    } catch {
      setError("產生邀請碼失敗，請稍後再試");
    }
  }

  if (!elders) return <p>載入中…</p>;
  return (
    <main>
      <h1>您管理的長輩</h1>
      {error && <p>{error}</p>}
      {notice && (
        <p>
          {notice.kind === "elder"
            ? "長輩綁定碼（請交給長輩在 LINE 貼上，24 小時內有效）："
            : "家屬邀請碼（請交給其他家屬在 LINE 貼上，24 小時內有效）："}
          <strong>{notice.code}</strong>
        </p>
      )}
      <ul>
        {elders.map((e) => (
          <li key={e.elder_id}>
            {e.name}：<Link to={`/elders/${e.elder_id}/medications`}>用藥</Link>
            {" / "}
            <Link to={`/elders/${e.elder_id}/appointments`}>回診</Link>
            {" / "}
            <button type="button" onClick={() => invite(e.elder_id)}>
              邀請家屬
            </button>
          </li>
        ))}
      </ul>
      <h2>新增長輩</h2>
      <input
        value={newName}
        onChange={(e) => setNewName(e.target.value)}
        placeholder="長輩稱呼（例：阿公、王媽媽）"
      />
      <button type="button" onClick={create}>
        建立
      </button>
    </main>
  );
}
