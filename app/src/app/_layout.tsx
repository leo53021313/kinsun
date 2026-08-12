import { Stack } from "expo-router";

import { SessionProvider } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, elder } from "@/lib/theme";

export default function RootLayout() {
  // SafeAreaProvider 不需自掛：expo-router 的 ExpoRoot 已內建（查證 ✅ 庚-32／F-14），
  // 各畫面的 SafeAreaView（react-native-safe-area-context）直接可用。
  return (
    <SessionProvider>
      <RootStack />
    </SessionProvider>
  );
}

/**
 * 長輩端走原生 header 的畫面共用這組設定。
 *
 * ⚠️ 規則 1「文字下限 22px」管的是**長輩看得到的每一段文字**，原生 header 的標題
 * 也算。全域 `screenOptions` 只設了 `fontWeight`，字級因此落在系統預設（約 17px）
 * ——比長輩端畫面內任何一個字都小。
 *
 * ⚠️ 不改全域 `screenOptions`：那會把家屬端的標題一起放大，而家屬端沒有這條下限。
 */
const elderHeaderOptions = {
  headerTitleStyle: { fontSize: elder.fontMin, fontWeight: "700" as const },
};

function RootStack() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTintColor: colors.text,
        contentStyle: { backgroundColor: colors.background },
        headerTitleStyle: { fontWeight: "700" },
      }}
    >
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="role" options={{ title: strings.nav.role }} />
      <Stack.Screen name="guardian" options={{ headerShown: false }} />
      <Stack.Screen
        name="guardian-detail/elder/[elderId]/index"
        options={{ title: strings.nav.elderDetail }}
      />
      <Stack.Screen
        name="guardian-detail/elder/[elderId]/schedules"
        options={{ title: strings.nav.schedules }}
      />
      <Stack.Screen
        name="guardian-detail/elder/[elderId]/summary"
        options={{ title: strings.nav.dailySummary }}
      />
      <Stack.Screen
        name="guardian-detail/schedule/[scheduleId]/edit"
        options={{ title: strings.nav.editAppointment }}
      />
      <Stack.Screen
        name="guardian-detail/alert/[eventId]"
        options={{ title: strings.nav.criticalAlert }}
      />
      <Stack.Screen name="auth/guardian-login" options={{ title: strings.nav.guardianLogin }} />
      <Stack.Screen
        name="auth/guardian-register"
        options={{ title: strings.nav.guardianRegister }}
      />
      <Stack.Screen
        name="elder/bind"
        options={{ title: strings.nav.elderBind, ...elderHeaderOptions }}
      />
      <Stack.Screen
        name="elder/login"
        options={{ title: strings.nav.elderLogin, ...elderHeaderOptions }}
      />
      <Stack.Screen name="elder/talk" options={{ headerShown: false }} />
      <Stack.Screen name="elder/history" options={{ headerShown: false }} />
      <Stack.Screen
        name="elder/notifications"
        options={{ title: strings.elderNotifications.title, ...elderHeaderOptions }}
      />
    </Stack>
  );
}
