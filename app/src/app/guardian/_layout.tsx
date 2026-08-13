/** 家屬端底部導航（批次 5）。
 *
 * 五個項目皆有圖示＋文字；中央黃色主鍵只是一個動作，不會把 add.tsx 留在返回堆疊。
 * 深層頁全部放在外層 guardian-detail Stack，因此進去時 tab bar 會消失。
 */

import {
  Redirect,
  Tabs,
  useFocusEffect,
  usePathname,
  useRouter,
} from "expo-router";
import { useCallback, useRef } from "react";
import { BellIcon } from "phosphor-react-native/src/icons/Bell";
import { ChartDonutIcon } from "phosphor-react-native/src/icons/ChartDonut";
import { HouseIcon } from "phosphor-react-native/src/icons/House";
import { PlusIcon } from "phosphor-react-native/src/icons/Plus";
import { UserCircleIcon } from "phosphor-react-native/src/icons/UserCircle";
import {
  ActivityIndicator,
  Alert,
  BackHandler,
  Platform,
  Pressable,
  type PressableProps,
  StyleSheet,
  Text,
  View,
} from "react-native";

import {
  GuardianTabsProvider,
  useGuardianTabsState,
} from "@/lib/GuardianTabsProvider";
import { useSession } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, radius, spacing } from "@/lib/theme";

export default function GuardianTabsLayout() {
  const { loading, session } = useSession();

  if (loading) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }
  if (!session || session.role !== "guardian") {
    return <Redirect href="/role" />;
  }

  return (
    <GuardianTabsProvider>
      <GuardianTabsNavigator />
    </GuardianTabsProvider>
  );
}

function GuardianTabsNavigator() {
  const router = useRouter();
  const pathname = usePathname();
  const openingAddRef = useRef(false);
  const { primaryElder, refreshPrimaryElder } = useGuardianTabsState();
  const profileLabel =
    primaryElder?.nickname?.trim() ||
    primaryElder?.name?.trim() ||
    strings.guardianTabs.profile;

  useFocusEffect(
    useCallback(() => {
      const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
        if (pathname !== "/guardian/home") {
          router.navigate("/guardian/home");
          return true;
        }
        return false;
      });
      return () => subscription.remove();
    }, [pathname, router]),
  );

  const openAddReminder = useCallback(async () => {
    if (openingAddRef.current) return;
    openingAddRef.current = true;
    try {
      // 按下當下重讀，避免家屬剛建立第一位長輩時仍拿到舊的空狀態。
      const result = await refreshPrimaryElder();
      if (result.error) {
        Alert.alert(strings.common.loadFailedShort, result.error);
        return;
      }
      if (!result.elder) {
        Alert.alert(strings.guardianHome.addElderSection, strings.guardianHome.empty);
        router.navigate("/guardian/home");
        return;
      }
      router.push({
        pathname: "/guardian-detail/elder/[elderId]/schedules",
        params: { elderId: result.elder.elder_id },
      });
    } finally {
      openingAddRef.current = false;
    }
  }, [refreshPrimaryElder, router]);

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
      <Tabs.Screen
        name="add"
        listeners={{
          tabPress: (event) => {
            event.preventDefault();
            void openAddReminder();
          },
        }}
        options={{
          title: strings.guardianTabs.add,
          tabBarButton: (props) => <CenterAction onPress={props.onPress} />,
        }}
      />
      <Tabs.Screen
        name="notifications"
        options={{
          title: strings.guardianTabs.notifications,
          lazy: false,
          tabBarIcon: ({ color }) => <BellIcon size={26} weight="bold" color={color} />,
          tabBarBadgeStyle: styles.badge,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: profileLabel,
          tabBarIcon: ({ color }) => <UserCircleIcon size={26} weight="bold" color={color} />,
        }}
      />
    </Tabs>
  );
}

function CenterAction(props: { onPress?: PressableProps["onPress"] }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={strings.guardianTabs.addA11y}
      onPress={props.onPress}
      style={styles.centerWrap}
      testID="guardian-add-tab"
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
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
  },
  bar: {
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    height: Platform.OS === "ios" ? 88 : 72,
    paddingTop: spacing.s + 2,
    paddingBottom: Platform.OS === "ios" ? 30 : spacing.s,
    shadowColor: "#2F3273",
    shadowOpacity: 0.05,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: -4 },
    elevation: 8,
  },
  item: { paddingVertical: 0 },
  label: { fontSize: 14, fontWeight: "600" },
  badge: { backgroundColor: colors.dangerBadge, fontSize: 13, fontWeight: "700" },
  centerWrap: {
    flex: 1,
    minHeight: 72,
    alignItems: "center",
    justifyContent: "flex-end",
    gap: spacing.xs,
  },
  centerButton: {
    width: 62,
    height: 62,
    borderRadius: radius.pill,
    backgroundColor: colors.action,
    alignItems: "center",
    justifyContent: "center",
    marginTop: -30,
    shadowColor: "#D6A820",
    shadowOpacity: 0.32,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
  centerPressed: { backgroundColor: colors.actionPressed, transform: [{ scale: 0.97 }] },
  centerLabel: { fontSize: 14, fontWeight: "700", color: colors.text },
});
