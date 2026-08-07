/** 家屬端底部導航（批次 5）。
 *
 * 從 Stack 改成 Tabs。五個項目＋中央凸出的黃色主鍵；
 * 每個圖示都有文字標籤（不用色彩單獨傳遞意義）。
 *
 * ⚠ 深層頁面（長輩詳情、行程管理、危急詳情、改回診）不在這個 Tabs 底下，
 *   它們仍是外層 Stack 的成員，進去時 tab bar 應該消失。
 */

import { Tabs } from "expo-router";
import { BellIcon } from "phosphor-react-native/src/icons/Bell";
import { ChartDonutIcon } from "phosphor-react-native/src/icons/ChartDonut";
import { HouseIcon } from "phosphor-react-native/src/icons/House";
import { PlusIcon } from "phosphor-react-native/src/icons/Plus";
import { UserCircleIcon } from "phosphor-react-native/src/icons/UserCircle";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "@/lib/theme";
import { strings } from "@/lib/strings";

export default function GuardianTabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primaryPressed,
        tabBarInactiveTintColor: colors.textSoft,
        tabBarStyle: styles.bar,
        tabBarLabelStyle: styles.label,
        tabBarItemStyle: styles.item,
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: strings.guardianTabs.home,
          tabBarIcon: ({ color }) => <HouseIcon size={26} weight="bold" color={color} />,
        }}
      />
      <Tabs.Screen
        name="report"
        options={{
          title: strings.guardianTabs.report,
          tabBarIcon: ({ color }) => <ChartDonutIcon size={26} weight="bold" color={color} />,
        }}
      />
      {/* 中央主鍵：不是分頁，是動作。用 tabBarButton 換掉預設按鈕。 */}
      <Tabs.Screen
        name="add"
        options={{
          title: strings.guardianTabs.add,
          tabBarButton: (props) => <CenterAction {...props} />,
        }}
      />
      <Tabs.Screen
        name="notifications"
        options={{
          title: strings.guardianTabs.notifications,
          tabBarIcon: ({ color }) => <BellIcon size={26} weight="bold" color={color} />,
          // 未讀數由畫面自己 setOptions，避免 layout 依賴 session
          tabBarBadgeStyle: styles.badge,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: strings.guardianTabs.profile,
          tabBarIcon: ({ color }) => <UserCircleIcon size={26} weight="bold" color={color} />,
        }}
      />
    </Tabs>
  );
}

/** 中央凸出的黃色圓鈕。每頁唯一的主要行動——新增用藥／回診提醒。 */
function CenterAction(props: { onPress?: (e: any) => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={strings.guardianTabs.addA11y}
      onPress={props.onPress}
      style={styles.centerWrap}
    >
      {({ pressed }) => (
        <>
          <View style={[styles.centerButton, pressed ? styles.centerPressed : null]}>
            <PlusIcon size={30} weight="bold" color={colors.text} />
          </View>
          <Text style={styles.centerLabel} maxFontSizeMultiplier={1.6}>
            {strings.guardianTabs.add}
          </Text>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    height: Platform.OS === "ios" ? 88 : 72,
    paddingTop: spacing.s + 2,
    paddingBottom: Platform.OS === "ios" ? 30 : spacing.s,
    // elevation.row 反向（陰影往上）
    shadowColor: "#2F3273",
    shadowOpacity: 0.05,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: -4 },
    elevation: 8,
  },
  item: { paddingVertical: 0 },
  label: { fontSize: 14, fontWeight: "600" },
  badge: { backgroundColor: colors.dangerBadge, fontSize: 13, fontWeight: "700" },
  centerWrap: { flex: 1, alignItems: "center", justifyContent: "flex-end", gap: spacing.xs },
  centerButton: {
    width: 62,
    height: 62,
    borderRadius: radius.pill,
    backgroundColor: colors.action,
    alignItems: "center",
    justifyContent: "center",
    marginTop: -30, // 凸出於 tab bar 之上
    shadowColor: "#D6A820",
    shadowOpacity: 0.32,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
  centerPressed: { backgroundColor: colors.actionPressed, transform: [{ scale: 0.97 }] },
  centerLabel: { fontSize: 14, fontWeight: "700", color: colors.text },
});
