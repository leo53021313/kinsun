/** 長輩端「之前聊過的」（批次 4）。
 *
 * 只顯示當天，資料源是本機的 todayLog，不打後端——
 * 跟隨短期記憶的界線，也不牴觸 api.ts 的「不開放逐字對話」。
 *
 * 版面規則同其他長輩端畫面：一屏內不捲動、文字 ≥ 22、沒有舞台只有頁首頭像。
 * 例外：當天輪次多到裝不下時，只有內容層可捲（頁首固定）。
 */

import { useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { useFocusEffect } from "expo-router";
import { ArrowLeftIcon } from "phosphor-react-native/src/icons/ArrowLeft";
import { SpeakerHighIcon } from "phosphor-react-native/src/icons/SpeakerHigh";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { BearAvatar } from "@/components/BearStage";
import { colors, elder, radius, spacing } from "@/lib/theme";
import { strings } from "@/lib/strings";
import { loadToday, type TodayTurn } from "@/lib/todayLog";

export default function ElderHistory() {
  const router = useRouter();
  const [turns, setTurns] = useState<TodayTurn[]>([]);
  const [loaded, setLoaded] = useState(false);

  // useFocusEffect 而非 useEffect：講完話回到這頁要看得到最新一輪
  useFocusEffect(
    useCallback(() => {
      let alive = true;
      (async () => {
        const list = await loadToday();
        if (alive) {
          setTurns(list);
          setLoaded(true);
        }
      })();
      return () => {
        alive = false;
      };
    }, []),
  );

  return (
    <SafeAreaView style={styles.screen} edges={["top", "bottom"]}>
      <View style={styles.header}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={strings.elderHistory.back}
          onPress={() => router.back()}
          style={({ pressed }) => [styles.roundButton, pressed ? styles.roundPressed : null]}
        >
          <ArrowLeftIcon size={28} weight="bold" color={colors.primary} />
        </Pressable>
        <Text style={styles.title} maxFontSizeMultiplier={2}>
          {strings.elderHistory.title}
        </Text>
        <BearAvatar />
      </View>

      <ScrollView
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
      >
        {loaded && turns.length === 0 ? (
          <Text style={styles.empty} maxFontSizeMultiplier={2}>
            {strings.elderHistory.empty}
          </Text>
        ) : null}

        {/* 最新的在最上面——長輩要找的通常是剛才那句 */}
        {[...turns].reverse().map((turn, index) => (
          <View key={turn.at} style={styles.card}>
            <Text style={styles.time} maxFontSizeMultiplier={2}>
              {formatTime(turn.at)}
            </Text>
            <Text style={styles.said} maxFontSizeMultiplier={2}>
              {strings.elderHistory.youSaid}
              {turn.said}
            </Text>
            <Text style={styles.reply} maxFontSizeMultiplier={2}>
              {strings.elderHistory.bearSaid}
              {turn.reply}
            </Text>
            {/* 只有最新一則給「再聽一次」——長輩不需要重播每一句，
                而且每則都放按鈕會讓畫面變成一排按鈕 */}
            {index === 0 ? (
              <Pressable
                accessibilityRole="button"
                onPress={() => replay(turn)}
                style={({ pressed }) => [styles.replay, pressed ? styles.replayPressed : null]}
              >
                <SpeakerHighIcon size={24} weight="bold" color={colors.primary} />
                <Text style={styles.replayLabel} maxFontSizeMultiplier={1.6}>
                  {strings.elderHistory.replay}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ))}

        {turns.length > 0 ? (
          <Text style={styles.footnote} maxFontSizeMultiplier={2}>
            {strings.elderHistory.footnote}
          </Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function formatTime(at: number): string {
  const d = new Date(at);
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, "0");
  const period = h < 12 ? "早上" : h < 18 ? "下午" : "晚上";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${period} ${hour12}:${m}`;
}

/** TODO（批次 3 接上）：重播用 replyAudio 快取的檔案。
 *  快取不在時退回 TTS 重新合成，長輩不該看到「檔案過期」這種訊息。 */
function replay(_turn: TodayTurn) {
  // 由 talk.tsx 的播放器實作；這裡先留接點
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    paddingHorizontal: elder.pagePadding,
    paddingTop: spacing.s,
    paddingBottom: spacing.m,
  },
  roundButton: {
    width: elder.roundButton,
    height: elder.roundButton,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  roundPressed: { backgroundColor: colors.background, transform: [{ scale: 0.98 }] },
  title: { flex: 1, fontSize: 28, fontWeight: "800", color: colors.text },
  list: {
    paddingHorizontal: elder.pagePadding,
    paddingBottom: spacing.xl,
    gap: spacing.s + 2,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.m - 2,
    gap: spacing.xs + 2,
    shadowColor: "#2F3273",
    shadowOpacity: 0.05,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 2,
  },
  time: { fontSize: elder.fontMin, fontWeight: "600", color: colors.textSoft },
  said: { fontSize: elder.fontMin, lineHeight: elder.fontMin * 1.4, color: colors.text },
  reply: { fontSize: elder.fontMin, lineHeight: elder.fontMin * 1.4, color: colors.primary },
  replay: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.s,
    minHeight: 52,
    paddingHorizontal: 20,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginTop: spacing.xs,
  },
  replayPressed: { backgroundColor: colors.background, transform: [{ scale: 0.98 }] },
  replayLabel: { fontSize: elder.fontMin, fontWeight: "700", color: colors.primary },
  empty: {
    fontSize: elder.fontMin,
    lineHeight: elder.fontMin * 1.5,
    color: colors.textSoft,
    paddingTop: spacing.l,
  },
  footnote: {
    fontSize: elder.fontMin,
    lineHeight: elder.fontMin * 1.45,
    color: colors.textSoft,
    paddingTop: spacing.xs,
  },
});
