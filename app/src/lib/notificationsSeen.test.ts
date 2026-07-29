/**
 * 已讀水位分角色（2026-07-29，X-01）。兩件事沒測就會靜默壞掉：
 * 一是家屬鍵名必須維持原樣，改了會讓既有裝置升版後未讀數整批復活；
 * 二是兩種角色必須各記各的，共用會讓長輩看完提醒後家屬的未讀數也被清掉
 * （內測模式的「切換身分」讓同一台裝置真的會有兩種角色）。
 */

import * as SecureStore from "expo-secure-store";

import { loadSeenAt, saveSeenAt } from "./notificationsSeen";

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
}));

const mocked = SecureStore as jest.Mocked<typeof SecureStore>;

beforeEach(() => {
  jest.clearAllMocks();
});

test("家屬沿用原鍵名（升版後未讀數不復活）", async () => {
  await saveSeenAt(1785260000, "guardian");
  expect(mocked.setItemAsync).toHaveBeenCalledWith("kinsun_notifications_seen_at", "1785260000");
});

test("未指定角色時預設家屬，與既有呼叫端相容", async () => {
  await saveSeenAt(1785260000);
  expect(mocked.setItemAsync).toHaveBeenCalledWith("kinsun_notifications_seen_at", "1785260000");
});

test("長輩用獨立鍵名，不會蓋掉家屬的水位", async () => {
  await saveSeenAt(1785270000, "elder");
  expect(mocked.setItemAsync).toHaveBeenCalledWith(
    "kinsun_elder_notifications_seen_at",
    "1785270000",
  );
});

test("讀取依角色取對應的鍵", async () => {
  mocked.getItemAsync.mockResolvedValue("1785260000");
  await loadSeenAt("elder");
  expect(mocked.getItemAsync).toHaveBeenCalledWith("kinsun_elder_notifications_seen_at");
});

test("從未存過回 0（新裝置全部算未讀）", async () => {
  mocked.getItemAsync.mockResolvedValue(null);
  await expect(loadSeenAt("elder")).resolves.toBe(0);
});

test("存到壞值回 0 而不是 NaN", async () => {
  mocked.getItemAsync.mockResolvedValue("不是數字");
  await expect(loadSeenAt("elder")).resolves.toBe(0);
});
