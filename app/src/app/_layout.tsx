import { Stack } from "expo-router";

import { SessionProvider } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors } from "@/lib/theme";

export default function RootLayout() {
  // SafeAreaProvider 不需自掛：expo-router 的 ExpoRoot 已內建（查證 ✅ 庚-32／F-14），
  // 各畫面的 SafeAreaView（react-native-safe-area-context）直接可用。
  return (
    <SessionProvider>
      <RootStack />
    </SessionProvider>
  );
}

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
      <Stack.Screen name="guardian/login" options={{ title: strings.nav.guardianLogin }} />
      <Stack.Screen name="guardian/register" options={{ title: strings.nav.guardianRegister }} />
      <Stack.Screen
        name="guardian/home"
        options={{ title: strings.nav.guardianHome, headerBackVisible: false }}
      />
      <Stack.Screen name="guardian/elder/[elderId]/index" options={{ title: strings.nav.elderDetail }} />
      <Stack.Screen name="guardian/elder/[elderId]/schedules" options={{ title: strings.nav.schedules }} />
      <Stack.Screen name="guardian/notifications" options={{ title: strings.nav.notifications }} />
      <Stack.Screen name="elder/bind" options={{ title: strings.nav.elderBind }} />
      <Stack.Screen name="elder/login" options={{ title: strings.nav.elderLogin }} />
      <Stack.Screen name="elder/talk" options={{ headerShown: false }} />
    </Stack>
  );
}
