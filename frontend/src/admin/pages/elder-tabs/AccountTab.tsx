import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { type AdminElderAccount, getElderAccount } from "../../api";
import { formatTime } from "../../format";

const INVITE_STATUS_LABELS: Record<string, string> = {
  active: "有效",
  used: "已使用",
  expired: "已過期",
  locked: "已鎖定（嘗試次數用完）",
};

/** 帳號與綁定分頁：排查「為什麼登不進去」——綁定、邀請碼、同意、帳密、token。 */
export function AccountTab() {
  const { elderId } = useParams<{ elderId: string }>();
  const [data, setData] = useState<AdminElderAccount | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    getElderAccount(elderId).then(setData, () => setError(true));
  }, [elderId]);

  useEffect(load, [load]);

  if (error) return <p className="error-banner">載入失敗，請重新整理。</p>;
  if (!data) return <p>載入中…</p>;
  return (
    <div>
      <h3>綁定通道</h3>
      {data.bindings.length === 0 && <p>尚未綁定任何通道。</p>}
      {data.bindings.map((b) => (
        <div className="card" key={`${b.channel}-${b.external_id}`}>
          <span className="badge badge-ok">{b.channel}</span> {b.external_id}
          <small className="timeline-time">　綁定於 {formatTime(b.created_at)}</small>
        </div>
      ))}
      <h3>帳號</h3>
      <div className="card">
        {data.has_password_account
          ? `已設定帳密登入（手機：${data.phone}）`
          : "尚未設定帳密登入（家屬可在 App 代辦）"}
        ｜有效 token：{data.tokens.length} 個
      </div>
      <h3>邀請碼</h3>
      {data.invites.length === 0 && <p>沒有邀請碼紀錄。</p>}
      {data.invites.map((i) => (
        <div className="card" key={i.code}>
          <strong>{i.code}</strong>　{i.role === "elder" ? "長輩綁定碼" : "家屬邀請碼"}
          {INVITE_STATUS_LABELS[i.status] ?? i.status}
          <small className="timeline-time">
            　到期 {formatTime(i.expires_at)}｜已嘗試 {i.attempts} 次
          </small>
        </div>
      ))}
      <h3>同意紀錄</h3>
      <div className="card">
        {data.consent
          ? `${data.consent.consent_by === "proxy" ? "家屬代辦" : "本人"}同意（版本 ${
              data.consent.version
            }）於 ${formatTime(data.consent.granted_at)}${
              data.consent.revoked_at ? `；已於 ${formatTime(data.consent.revoked_at)} 撤回` : ""
            }`
          : "尚無同意紀錄"}
      </div>
      <h3>家屬連結</h3>
      {data.guardians.length === 0 && <p>尚無家屬連結。</p>}
      {data.guardians.map((g) => (
        <div className="card" key={g.guardian_id}>
          {g.name}（{g.role}）　升級順位 {g.escalation_order}
        </div>
      ))}
    </div>
  );
}
