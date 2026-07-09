import { Stack } from "expo-router";

import { colors } from "@/lib/theme";

export default function RootLayout() {
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
      <Stack.Screen name="role" options={{ title: "選擇身分" }} />
      <Stack.Screen name="guardian/login" options={{ title: "家屬登入" }} />
      <Stack.Screen name="guardian/register" options={{ title: "家屬註冊" }} />
      <Stack.Screen
        name="guardian/home"
        options={{ title: "我的長輩", headerBackVisible: false }}
      />
      <Stack.Screen name="guardian/elder/[elderId]" options={{ title: "長輩詳情" }} />
      <Stack.Screen name="guardian/notifications" options={{ title: "通知" }} />
      <Stack.Screen name="elder/bind" options={{ title: "輸入綁定碼" }} />
      <Stack.Screen name="elder/talk" options={{ headerShown: false }} />
    </Stack>
  );
}
