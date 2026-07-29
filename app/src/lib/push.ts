/**
 * 裝置推播註冊（真推播 D-08 階段 5，2026-07-29）。
 *
 * 為什麼要有這一層而不是直接在畫面裡呼叫 expo-notifications：取 token 這件事有
 * 四個必須照順序處理的前提（模擬器不支援、Android 13 要先建頻道、權限可能被拒、
 * projectId 可能沒設），任何一個沒處理都會在真機上安靜地拿不到 token——而症狀
 * 只有「提醒不會響」，跟伺服器沒送、網路不通看起來一模一樣。
 *
 * ⚠️ 推播在 Expo Go 完全不能用（SDK 53 起移除）。必須用 development build，
 * 否則 getExpoPushTokenAsync 會直接拋錯。這裡把它降級成回 null＋一行 warn，
 * 讓開發時用 Expo Go 跑其他功能不受影響。
 */

import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { registerPushToken, removePushToken } from "./api";

/** Android 通知頻道 id。Android 8+ 沒有頻道就不會顯示通知。 */
const CHANNEL_ID = "reminders";

export type PushPlatform = "android" | "ios";

/** 前景收到推播時仍然出聲——長輩可能正開著 App 但沒在看螢幕。 */
export function configureForegroundBehaviour(): void {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldPlaySound: true,
      shouldSetBadge: false,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
}

function projectId(): string {
  return (
    (Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined)?.eas?.projectId ??
    (Constants as { easConfig?: { projectId?: string } }).easConfig?.projectId ??
    ""
  );
}

/**
 * 取得這台裝置的 Expo push token。拿不到一律回 null（不拋），呼叫端據此略過註冊。
 *
 * 回 null 的四種情形都會留一行 warn，因為它們在真機上的症狀完全相同（提醒不響），
 * 沒有日誌就只能靠猜。
 */
export async function getPushToken(): Promise<string | null> {
  if (!Device.isDevice) {
    console.warn("[push] 模擬器不支援推播，略過註冊");
    return null;
  }
  // Android 13+：頻道必須在取 token 之前建好，否則拿不到 token。
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
      name: "金孫的提醒",
      importance: Notifications.AndroidImportance.HIGH,
      // 長輩常把手機放在旁邊沒看螢幕，震動比視覺提示重要。
      vibrationPattern: [0, 250, 250, 250],
    });
  }
  const existing = await Notifications.getPermissionsAsync();
  let granted = existing.granted;
  if (!granted && existing.canAskAgain) {
    granted = (await Notifications.requestPermissionsAsync()).granted;
  }
  if (!granted) {
    console.warn("[push] 使用者未授權通知，略過註冊");
    return null;
  }
  const id = projectId();
  if (!id) {
    console.warn("[push] 找不到 EAS projectId（尚未 eas init？），略過註冊");
    return null;
  }
  try {
    return (await Notifications.getExpoPushTokenAsync({ projectId: id })).data;
  } catch (exc) {
    // Expo Go 會走到這裡（SDK 53 起不支援推播）。
    console.warn("[push] 取得推播 token 失敗（Expo Go 不支援推播，需 development build）", exc);
    return null;
  }
}

/**
 * 登入後把這台裝置登記到伺服器。整段失敗都只記 log——推播是加分項，
 * 註冊不成功長輩打開 App 仍然看得到提醒，不可因此擋住任何畫面。
 */
export async function registerDeviceForPush(sessionToken: string): Promise<void> {
  try {
    const token = await getPushToken();
    if (!token) {
      return;
    }
    await registerPushToken(sessionToken, token, Platform.OS as PushPlatform);
  } catch (exc) {
    console.warn("[push] 裝置註冊失敗（提醒仍會落在 App 內）", exc);
  }
}

/** 登出時解除登記，避免提醒繼續推到已經不是本人在用的裝置。 */
export async function unregisterDeviceForPush(sessionToken: string): Promise<void> {
  try {
    const token = await getPushToken();
    if (!token) {
      return;
    }
    await removePushToken(sessionToken, token);
  } catch (exc) {
    console.warn("[push] 解除裝置登記失敗", exc);
  }
}
