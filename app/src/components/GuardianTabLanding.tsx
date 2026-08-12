/**
 * ⚠️ 本頁的按鈕一律 `outline`：規則 14「暖黃是每頁唯一主要行動」，而分頁
 * 底部常駐著中央凸出的暖黃鍵。頁內再放暖黃就是一屏兩個主要行動。
 */

import { useRouter } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Section } from "@/components/ui";
import { useGuardianTabsState } from "@/lib/GuardianTabsProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

export function GuardianTabLanding(props: { title: string; actionLabel: string }) {
  const router = useRouter();
  const { primaryElder, loaded, error, refreshPrimaryElder } = useGuardianTabsState();
  const elderName = primaryElder?.nickname?.trim() || primaryElder?.name?.trim() || "";

  return (
    <View style={styles.screen}>
      <Section title={props.title}>
        {!loaded ? <EmptyHint text={strings.common.loading} /> : null}
        <ErrorText message={error} />
        {loaded && !error && !primaryElder ? (
          <>
            <EmptyHint text={strings.guardianHome.empty} />
            <Button
              label={strings.guardianHome.addElderSection}
              variant="outline"
              onPress={() => router.navigate("/guardian/home")}
            />
          </>
        ) : null}
        {primaryElder ? (
          <>
            <Text style={styles.elderName}>{elderName}</Text>
            <Button
              label={props.actionLabel}
              variant="outline"
              onPress={() =>
                router.push({
                  pathname: "/guardian-detail/elder/[elderId]",
                  params: { elderId: primaryElder.elder_id },
                })
              }
            />
          </>
        ) : null}
        {error ? (
          <Button
            label={strings.common.retry}
            variant="subtle"
            onPress={() => void refreshPrimaryElder()}
          />
        ) : null}
      </Section>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background, padding: spacing.m },
  elderName: { fontSize: 22, fontWeight: "800", color: colors.text },
});
