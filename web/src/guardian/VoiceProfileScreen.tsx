/**
 * 家屬錄一段參考語音，長輩往後就聽到那個聲音。
 *
 * ⚠️ **為什麼一定要能試聽**：後端的 `GET` 端點刻意不回音檔也不回可下載網址
 * （那是長輩家人的聲音樣本，查狀態不需要能把它拿走）。送出之後就再也沒有任何
 * 辦法聽到自己錄了什麼——沒有試聽就是盲送，而錄音品質決定長輩往後聽到的每一句話。
 *
 * ⚠️ 試聽用原生 `<audio controls>` 而不是 `talk/playback.ts`：後者帶著綁長輩
 * 播放器生命週期的模組級待撤銷佇列（`revokeQueuedReplyAudio`），雙欄舞台上兩欄
 * 同時掛載時會互相干擾。原生控制項另外免費解決 iOS 音訊解鎖（播放是直接的使用者
 * 手勢，不需要 `audioUnlock`）與鍵盤／讀螢幕支援。代價是外觀為瀏覽器預設樣式。
 */

import { useCallback, useEffect, useState } from "react";

import type { VoiceProfileScript, VoiceProfileStatus } from "kinsun-shared/types";

import { ApiError, apiErrorMessage } from "@/api";
import { GuardianSession } from "@/session/contexts";
import { strings } from "@/strings";
import { probeMicrophone, type MicrophoneProbeResult } from "@/talk/recorder";
import { Button } from "@/ui/Button";
import { ErrorText, NoticeText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { Section } from "@/ui/Section";

import {
  getVoiceProfile,
  getVoiceProfileScript,
  revokeVoiceProfile,
  setVoiceProfile,
} from "./api";
import { useVoiceRecording } from "./useVoiceRecording";

/** 麥克風五種失敗各自的白話說明；`granted` 沒有訊息，故從鍵集合裡排除。 */
const MIC_MESSAGES: Record<Exclude<MicrophoneProbeResult, "granted">, string> = {
  denied: strings.voiceProfile.micDenied,
  "not-found": strings.voiceProfile.micNotFound,
  "in-use": strings.voiceProfile.micInUse,
  "insecure-origin": strings.voiceProfile.micInsecure,
  unsupported: strings.voiceProfile.micUnsupported,
};

function formatGrantedAt(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleDateString("zh-TW");
}

export function VoiceProfileScreen(props: { elderId: string; elderName: string }) {
  const { session } = GuardianSession.useSession();
  const token = session?.token ?? "";

  const [script, setScript] = useState<VoiceProfileScript | null>(null);
  const [status, setStatus] = useState<VoiceProfileStatus | null>(null);
  const [loadError, setLoadError] = useState("");
  const [micIssue, setMicIssue] = useState("");
  const [consentedBy, setConsentedBy] = useState(session?.display_name ?? "");
  const [hasConsent, setHasConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const recording = useVoiceRecording();

  useEffect(() => {
    let alive = true;
    void getVoiceProfileScript()
      .then((value) => alive && setScript(value))
      .catch(() => alive && setLoadError(strings.voiceProfile.loadFailed));
    void getVoiceProfile(props.elderId, token)
      .then((value) => alive && setStatus(value))
      // ⚠️ 讀不到就要講：靜默當成「沒設定過」的話，家屬會以為聲音沒設定成功、
      // 重錄一次把原本好好的那一份覆蓋掉。
      .catch(() => alive && setLoadError(strings.voiceProfile.loadFailed));
    // ⚠️ 進畫面就問權限，不等按下錄音鍵：權限對話框跳出來的當下會吃掉第一次
    // 錄音（長輩端 2026-07-18 在 iOS 上踩過，見 docs/dev/17）。
    void probeMicrophone().then((result) => {
      if (alive && result !== "granted") {
        setMicIssue(MIC_MESSAGES[result]);
      }
    });
    return () => {
      alive = false;
    };
  }, [props.elderId, token]);

  const beginRecording = useCallback(async () => {
    setError("");
    setMessage("");
    const started = await recording.start();
    if (started) {
      setMicIssue("");
      return;
    }
    // 進畫面的探測過了、真的要錄卻失敗：權限可能剛被撤掉，或麥克風被別的程式
    // 搶走。重探一次才講得出正確的原因，而不是一句籠統的「錄音失敗」。
    const result = await probeMicrophone();
    setMicIssue(result === "granted" ? strings.voiceProfile.micInUse : MIC_MESSAGES[result]);
  }, [recording]);

  async function submit() {
    if (recording.audio === null) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const next = await setVoiceProfile(
        props.elderId,
        recording.audio,
        recording.mimeType,
        consentedBy.trim(),
        token,
      );
      setStatus(next);
      recording.reset();
      setHasConsent(false);
      setMessage(strings.voiceProfile.submitted);
    } catch (exc) {
      setError(
        exc instanceof ApiError && exc.status === 413
          ? strings.voiceProfile.tooLarge
          : apiErrorMessage(exc, strings.voiceProfile.submitFailed),
      );
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!window.confirm(strings.voiceProfile.revokeConfirm)) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await revokeVoiceProfile(props.elderId, token);
      setStatus({ elder_id: props.elderId, has_profile: false });
      setMessage(strings.voiceProfile.revoked);
    } catch (exc) {
      // ⚠️ 撤銷失敗不要樂觀切換畫面：家屬會以為聲音已經停用了，而它還在用。
      setError(apiErrorMessage(exc, strings.voiceProfile.revokeFailed));
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = recording.isLongEnough && hasConsent && consentedBy.trim().length > 0 && !busy;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-4">
      <h1 className="text-lg font-bold text-ink">{strings.voiceProfile.title}</h1>
      <p className="text-sm leading-6 text-ink-soft">{strings.voiceProfile.intro}</p>

      {loadError ? <ErrorText message={loadError} /> : null}
      {micIssue ? <ErrorText message={micIssue} /> : null}
      {message ? <NoticeText message={message} /> : null}

      {status?.has_profile ? (
        <Section title={strings.voiceProfile.currentSection}>
          <p className="text-sm text-ink">
            {strings.voiceProfile.setHint(
              status.consented_by ?? "",
              status.granted_at ? formatGrantedAt(status.granted_at) : "",
            )}
          </p>
          <Button
            label={strings.voiceProfile.revoke}
            variant="danger"
            busy={busy}
            onClick={() => void revoke()}
          />
        </Section>
      ) : null}

      <Section title={strings.voiceProfile.scriptLabel}>
        {script === null ? (
          <p className="text-sm text-ink-soft">{strings.common.loading}</p>
        ) : (
          <p className="text-xl leading-9 text-ink">{script.script}</p>
        )}
      </Section>

      {script !== null && script.tips.length > 0 ? (
        <Section title={strings.voiceProfile.tipsLabel}>
          <ul className="list-disc pl-5 text-sm leading-6 text-ink-soft">
            {script.tips.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section>
        {recording.status === "recording" ? (
          <>
            <p className="text-sm text-ink">
              {strings.voiceProfile.elapsed(Math.floor(recording.durationMs / 1000))}
            </p>
            <Button label={strings.voiceProfile.stop} onClick={() => void recording.stop()} />
          </>
        ) : (
          <Button
            label={
              recording.status === "recorded"
                ? strings.voiceProfile.rerecord
                : strings.voiceProfile.start
            }
            variant={recording.status === "recorded" ? "outline" : "primary"}
            onClick={() => void beginRecording()}
          />
        )}

        {recording.status === "recorded" && !recording.isLongEnough ? (
          <ErrorText message={strings.voiceProfile.tooShort} />
        ) : null}

        {recording.previewUri !== null ? (
          <div className="flex flex-col gap-1">
            <span className="text-sm text-ink-soft">{strings.voiceProfile.previewLabel}</span>
            {/* 原生控制項：見檔頭說明。 */}
            <audio controls src={recording.previewUri} className="w-full" />
          </div>
        ) : null}
      </Section>

      <Section>
        <Field
          label={strings.voiceProfile.consentLabel}
          value={consentedBy}
          onChange={setConsentedBy}
          hint={strings.voiceProfile.consentHint}
        />
        <label className="flex items-start gap-2 text-sm leading-6 text-ink">
          <input
            type="checkbox"
            checked={hasConsent}
            onChange={(event) => setHasConsent(event.target.checked)}
            className="mt-1"
          />
          <span>{strings.voiceProfile.consentCheckbox}</span>
        </label>
        {error ? <ErrorText message={error} /> : null}
        <Button
          label={strings.voiceProfile.submit}
          disabled={!canSubmit}
          busy={busy}
          onClick={() => void submit()}
        />
      </Section>
    </div>
  );
}
