import { useCallback } from "react";
import { useParams } from "react-router-dom";

import { getElderAccount } from "../../api";
import { formatTime } from "../../format";
import { strings } from "../../strings";
import { useLoadable } from "../../useLoadable";

/** 帳號與綁定分頁：排查「為什麼登不進去」——綁定、邀請碼、同意、帳密、token。 */
export function AccountTab() {
  const { elderId } = useParams<{ elderId: string }>();
  const { data, error } = useLoadable(
    useCallback(() => (elderId ? getElderAccount(elderId) : null), [elderId]),
  );

  if (error) return <p className="error-banner">{strings.common.loadFailedRefresh}</p>;
  if (!data) return <p>{strings.common.loading}</p>;
  const account = strings.elderTabs.account;
  return (
    <div>
      <h3>{account.bindingsHeading}</h3>
      {data.bindings.length === 0 && <p>{account.noBindings}</p>}
      {data.bindings.map((b) => (
        <div className="card" key={`${b.channel}-${b.external_id}`}>
          <span className="badge badge-ok">{b.channel}</span> {b.external_id}
          <small className="timeline-time">
            　{account.boundAtPrefix} {formatTime(b.created_at)}
          </small>
        </div>
      ))}
      <h3>{account.accountHeading}</h3>
      <div className="card">
        {data.has_password_account
          ? account.passwordAccount(data.phone)
          : account.noPasswordAccount}
        {account.validTokenLine(data.tokens.length)}
      </div>
      <h3>{account.invitesHeading}</h3>
      {data.invites.length === 0 && <p>{account.noInvites}</p>}
      {data.invites.map((i) => (
        <div className="card" key={i.code}>
          <strong>{i.code}</strong>　
          {i.role === "elder" ? account.inviteRoleElder : account.inviteRoleGuardian}
          {account.inviteStatus[i.status] ?? i.status}
          <small className="timeline-time">
            　{account.inviteMeta(formatTime(i.expires_at), i.attempts)}
          </small>
        </div>
      ))}
      <h3>{account.consentHeading}</h3>
      <div className="card">
        {data.consent
          ? account.consentRecord({
              isProxy: data.consent.consent_by === "proxy",
              version: data.consent.version,
              grantedAt: formatTime(data.consent.granted_at),
              revokedAt: data.consent.revoked_at ? formatTime(data.consent.revoked_at) : null,
            })
          : account.noConsent}
      </div>
      <h3>{account.guardiansHeading}</h3>
      {data.guardians.length === 0 && <p>{account.noGuardians}</p>}
      {data.guardians.map((g) => (
        <div className="card" key={g.guardian_id}>
          {g.name}（{g.role}）　{account.escalationPrefix} {g.escalation_order}
        </div>
      ))}
    </div>
  );
}
