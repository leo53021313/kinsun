import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { loadSession, type Session } from "@/lib/auth";
import { colors } from "@/lib/theme";

/** 啟動導向：依儲存的身分自動進入家屬或長輩介面；無登入則選角色。 */
export default function Index() {
  const [state, setState] = useState<{ loading: boolean; session: Session | null }>({
    loading: true,
    session: null,
  });

  useEffect(() => {
    loadSession().then((session) => setState({ loading: false, session }));
  }, []);

  if (state.loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }
  if (state.session?.role === "guardian") {
    return <Redirect href="/guardian/home" />;
  }
  if (state.session?.role === "elder") {
    return <Redirect href="/elder/talk" />;
  }
  return <Redirect href="/role" />;
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
});
