import { Redirect } from "expo-router";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { useSession } from "@/lib/SessionProvider";
import { colors } from "@/lib/theme";

/** 啟動導向：依儲存的身分自動進入家屬或長輩介面；無登入則選角色。 */
export default function Index() {
  const { loading, session } = useSession();

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }
  if (session?.role === "guardian") {
    return <Redirect href="/guardian/home" />;
  }
  if (session?.role === "elder") {
    return <Redirect href="/elder/talk" />;
  }
  return <Redirect href="/role" />;
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
});
