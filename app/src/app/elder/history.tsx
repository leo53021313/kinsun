/** 長輩端「之前聊過的」（批次 4）。
 *
 * 只顯示當天，資料源是本機的 todayLog，不打後端。版面固定頁首，只有
 * 對話內容層可在內容超出時捲動；長輩端文字不設系統字級放大上限。
 */

import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ArrowLeftIcon } from "phosphor-react-native/src/icons/ArrowLeft";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { BearAvatar } from "@/components/BearStage";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, elder, radius, spacing } from "@/lib/theme";
import { loadToday, type TodayTurn } from "@/lib/todayLog";

export default function ElderHistory() {
  const router = useRouter();
  const { loading: sessionLoading, session } = useSession();
  const [turns, setTurns] = useState<TodayTurn[]>([]);
  const [loaded, setLoaded] = useState(false);
  const canReadHistory = !sessionLoading && session?.role === "elder";

  // useFocusEffect 而非 useEffect：講完話回到這頁時要載入最新一輪。
  useFocusEffect(
    useCallback(() => {
      if (sessionLoading) {
        return;
      }
      if (!session || session.role !== "elder") {
        setTurns([]);
        setLoaded(false);
        router.replace("/role");
        return;
      }

      let alive = true;
      void loadToday().then((list) => {
        if (alive) {
          setTurns(list);
          setLoaded(true);
        }
      });
      return () => {
        alive = false;
      };
    }, [router, sessionLoading, session]),
  );

  function goBackToTalk() {
    if (router.canGoBack()) {
      router.back();
      return;
    }
    // 直接由深層連結進入時沒有上一頁，仍回對講機而不是身分選擇頁。
    router.replace("/elder/talk");
  }

  return (
    <SafeAreaView style={styles.screen} edges={["top", "bottom"]}>
      <View style={styles.header} testID="elder-history-header">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={strings.elderHistory.back}
          onPress={goBackToTalk}
          style={({ pressed }) => [styles.roundButton, pressed ? styles.roundPressed : null]}
          testID="elder-history-back"
        >
          <ArrowLeftIcon size={28} weight="bold" color={colors.primary} />
        </Pressable>
        <Text style={styles.title}>{strings.elderHistory.title}</Text>
        <BearAvatar />
      </View>

      <ScrollView
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        testID="elder-history-content"
      >
        {canReadHistory && loaded && turns.length === 0 ? (
          <Text style={styles.empty}>{strings.elderHistory.empty}</Text>
        ) : null}

        {/* todayLog 依完成順序附加；反轉副本後，最新一輪會在最上面。 */}
        {canReadHistory
          ? [...turns].reverse().map((turn, index) => (
              <View
                key={`${turn.at}:${index}`}
                style={styles.card}
                testID={`elder-history-turn-${index}`}
              >
                <Text style={styles.time}>{formatHistoryTime(turn.at)}</Text>
                <Text style={styles.said}>
                  {strings.elderHistory.youSaid}
                  {turn.said}
                </Text>
                <Text style={styles.reply}>
                  {strings.elderHistory.bearSaid}
                  {turn.reply}
                </Text>
              </View>
            ))
          : null}

        {canReadHistory && turns.length > 0 ? (
          <Text style={styles.footnote}>{strings.elderHistory.footnote}</Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function formatHistoryTime(at: number): string {
  const date = new Date(at);
  const hour = date.getHours();
  const minute = String(date.getMinutes()).padStart(2, "0");
  const period = hour < 12 ? "早上" : hour < 18 ? "下午" : "晚上";
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${period} ${hour12}:${minute}`;
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
