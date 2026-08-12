import { Redirect } from "expo-router";

/** 中央黃鍵由 Tabs 的 tabPress 攔截；直接深連此路由時安全回首頁，不留空白頁。 */
export default function GuardianAddFallback() {
  return <Redirect href="/guardian/home" />;
}
