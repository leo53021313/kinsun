/** 危急通知詳情（批次 6 補件）。
 *
 * 依 handoff/危急通知詳情-後端規格.md 的型別寫成。
 * ⚠ 後端端點尚未實作——`loadDetail` 會 404，畫面會顯示載入失敗。
 *   要先看版面可把 USE_FIXTURE 打開。
 *
 * 給的是證據，不是結論：錄音、原始對話、阿白做了什麼、通知送給了誰。
 * 「這不算危急」是必要的回饋出口——誤判要能被家屬修正，
 * 否則家屬會學會忽略通知，安全雷達就失效了。
 */

import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Linking } from "react-native";
import { ClockCountdownIcon } from "phosphor-react-native/src/icons/ClockCountdown";
import { CheckCircleIcon } from "phosphor-react-native/src/icons/CheckCircle";
import { PhoneIcon } from "phosphor-react-native/src/icons/Phone";
import { PlayIcon } from "phosphor-react-native/src/icons/Play";
import { WarningCircleIcon } from "phosphor-react-native/src/icons/WarningCircle";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, Section, StatusPill } from "@/components/ui";
import { useSession } from "@/lib/SessionProvider";
import { colors, radius, spacing } from "@/lib/theme";
import { strings } from "@/lib/strings";

// TODO：後端補完後改成 import { getRiskEventDetail, handleRiskEvent, dismissRiskEvent } from "@/lib/api";
type RiskTranscriptTurn = { speaker: "elder" | "bear"; text: string; at: number };
type RiskDelivery = {
  guardian_id: string;
  name: string;
  delivered_at: number | null;
  read_at: number | null;
  scheduled_at: number | null;
};
type RiskEventDetail = {
  event_id: string;
  tier: number;
  reason: string;
  created_at: number;
  transcript: RiskTranscriptTurn[];
  audio_url: string | null;
  audio_duration_ms: number | null;
  deliveries: RiskDelivery[];
  handled_at: number | null;
  handled_by: string | null;
  dismissed_at: number | null;
};

export default function CriticalAlertDetail() {
  const router = useRouter();
  const { eventId, elderId, elderPhone } = useLocalSearchParams<{
    eventId: string;
    elderId: string;
    elderPhone?: string;
  }>();
  const { session } = useSession();
  const [detail, setDetail] = useState<RiskEventDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!session || !eventId) return;
    let alive = true;
    (async () => {
      try {
        // TODO：接上 getRiskEventDetail(elderId, eventId, session.token)
        throw new Error("not implemented");
      } catch {
        if (alive) setError(strings.common.loadFailed);
      }
    })();
    return () => {
      alive = false;
    };
  }, [session, eventId, elderId]);

  async function markHandled() {
    setBusy(true);
    try {
      // TODO：handleRiskEvent — 會一併取消尚未送出的第二順位通知
      router.back();
    } finally {
      setBusy(false);
    }
  }

  async function markNotCritical() {
    setBusy(true);
    try {
      // TODO：dismissRiskEvent — 這個回饋要進評估資料，誤判率是安全雷達唯一可信的品質指標
      router.back();
    } finally {
      setBusy(false);
    }
  }

  if (error && !detail) {
    return (
      <View style={styles.emptyScreen}>
        <EmptyHint text={error} />
      </View>
    );
  }

  const unhandled = detail && !detail.handled_at && !detail.dismissed_at;

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <StatusPill
          tone="critical"
          label={unhandled ? strings.criticalAlert.unhandled : strings.criticalAlert.badge}
          icon={<WarningCircleIcon size={20} weight="bold" color={colors.dangerText} />}
        />

        <Text style={styles.title} maxFontSizeMultiplier={2}>
          {detail?.reason ?? ""}
        </Text>

        {/* 一｜當時的錄音 */}
        <Section title={strings.criticalAlert.recordingSection}>
          {detail?.audio_url ? (
            <View style={styles.player}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={strings.criticalAlert.playRecording}
                style={styles.playButton}
              >
                <PlayIcon size={24} weight="bold" color="#FFFFFF" />
              </Pressable>
              {/* 波形是示意的——用 duration 畫等寬長條，不是真的取樣 */}
              <View style={styles.waveform}>
                {Array.from({ length: 11 }).map((_, i) => (
                  <View key={i} style={[styles.wave, { height: 12 + ((i * 7) % 28) }]} />
                ))}
              </View>
              <Text style={styles.duration} maxFontSizeMultiplier={1.6}>
                {formatDuration(detail.audio_duration_ms)}
              </Text>
            </View>
          ) : (
            <EmptyHint text={strings.criticalAlert.noRecording} />
          )}
        </Section>

        {/* 二｜當時的對話。危急逐字例外的核心——只有這一輪，不是整天。 */}
        <Section title={strings.criticalAlert.transcriptSection}>
          {(detail?.transcript ?? []).map((turn, i) => (
            <View
              key={i}
              style={[styles.bubbleRow, turn.speaker === "bear" ? styles.bubbleRowRight : null]}
            >
              <View
                style={[styles.bubble, turn.speaker === "bear" ? styles.bubbleBear : styles.bubbleElder]}
              >
                <Text style={styles.bubbleText} maxFontSizeMultiplier={2}>
                  {turn.text}
                </Text>
              </View>
              <Text style={styles.bubbleMeta} maxFontSizeMultiplier={1.6}>
                {turn.speaker === "bear" ? "阿白" : "長輩"}　{formatTime(turn.at)}
              </Text>
            </View>
          ))}
          <Text style={styles.note} maxFontSizeMultiplier={2}>
            {strings.criticalAlert.noJudgement}
          </Text>
        </Section>

        {/* 三｜通知送給了誰。下一位何時會收到也要寫清楚。 */}
        <Section title={strings.criticalAlert.deliverySection}>
          {(detail?.deliveries ?? []).map((d) => (
            <View key={d.guardian_id} style={styles.deliveryRow}>
              {d.delivered_at ? (
                <CheckCircleIcon size={20} weight="bold" color={colors.success} />
              ) : (
                <ClockCountdownIcon size={20} weight="bold" color={colors.warning} />
              )}
              <Text style={styles.deliveryText} maxFontSizeMultiplier={2}>
                {d.delivered_at
                  ? strings.criticalAlert.delivered(d.name, formatTime(d.delivered_at))
                  : strings.criticalAlert.scheduled(d.name, formatTime(d.scheduled_at ?? 0))}
              </Text>
            </View>
          ))}
        </Section>
      </ScrollView>

      {/* 主要行動仍是黃色——嚴重度與行動分屬兩個顏色角色 */}
      <View style={styles.footer}>
        <Button
          label={strings.criticalAlert.callElder}
          busy={busy}
          onPress={() => elderPhone && Linking.openURL(`tel:${elderPhone}`)}
        />
        <View style={styles.footerRow}>
          <View style={styles.footerHalf}>
            <Button label={strings.criticalAlert.handled} variant="outline" onPress={markHandled} />
          </View>
          <View style={styles.footerHalf}>
            <Button
              label={strings.criticalAlert.notCritical}
              variant="outline"
              onPress={markNotCritical}
            />
          </View>
        </View>
      </View>
    </View>
  );
}

function formatTime(at: number): string {
  if (!at) return "";
  const d = new Date(at);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function formatDuration(ms: number | null): string {
  if (!ms) return "";
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  emptyScreen: { flex: 1, backgroundColor: colors.background, padding: spacing.m },
  content: { padding: spacing.m, gap: spacing.m, paddingBottom: spacing.xl },
  title: { fontSize: 22, lineHeight: 32, fontWeight: "800", color: colors.text },
  player: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.s + 6,
    backgroundColor: colors.background,
    borderRadius: radius.control,
    padding: spacing.m,
  },
  playButton: {
    width: 52,
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  waveform: { flex: 1, flexDirection: "row", alignItems: "center", gap: 3, height: 40 },
  wave: { flex: 1, borderRadius: radius.pill, backgroundColor: "#C9CAE6" },
  duration: { fontSize: 16, fontWeight: "700", color: colors.textSoft },
  bubbleRow: { gap: spacing.xs, maxWidth: "88%" },
  bubbleRowRight: { alignSelf: "flex-end", alignItems: "flex-end" },
  bubble: { borderRadius: 18, paddingHorizontal: spacing.m, paddingVertical: 12 },
  bubbleElder: { backgroundColor: colors.background, borderBottomLeftRadius: 6 },
  bubbleBear: { backgroundColor: "#FDF6DE", borderBottomRightRadius: 6 },
  bubbleText: { fontSize: 17, lineHeight: 26, color: colors.text },
  bubbleMeta: { fontSize: 14, fontWeight: "600", color: colors.textSoft },
  note: { fontSize: 16, lineHeight: 24, color: colors.textSoft },
  deliveryRow: { flexDirection: "row", alignItems: "center", gap: spacing.s + 2 },
  deliveryText: { flex: 1, fontSize: 17, color: colors.text },
  footer: {
    padding: spacing.m,
    paddingBottom: 34,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: spacing.s + 2,
  },
  footerRow: { flexDirection: "row", gap: spacing.s + 2 },
  footerHalf: { flex: 1 },
});
