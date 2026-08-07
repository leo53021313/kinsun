import AsyncStorage from "@react-native-async-storage/async-storage";

import { appendTurn, clearToday, loadToday } from "./todayLog";

jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
}));

const storage = AsyncStorage as jest.Mocked<typeof AsyncStorage>;
let stored: string | null;

beforeEach(async () => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date("2026-08-07T10:00:00+08:00"));
  stored = null;
  jest.clearAllMocks();
  storage.getItem.mockImplementation(async () => stored);
  storage.setItem.mockImplementation(async (_key, value) => {
    stored = value;
  });
  storage.removeItem.mockImplementation(async () => {
    stored = null;
  });
  await clearToday();
  jest.clearAllMocks();
});

afterEach(() => {
  jest.useRealTimers();
});

test("同時完成三輪仍保留三筆真實你說與阿白回答", async () => {
  await Promise.all([
    appendTurn({ at: 1, said: "第一句", reply: "第一個回答" }),
    appendTurn({ at: 2, said: "第二句", reply: "第二個回答" }),
    appendTurn({ at: 3, said: "第三句", reply: "第三個回答" }),
  ]);

  await expect(loadToday()).resolves.toEqual([
    { at: 1, said: "第一句", reply: "第一個回答" },
    { at: 2, said: "第二句", reply: "第二個回答" },
    { at: 3, said: "第三句", reply: "第三個回答" },
  ]);
});

test("跨到裝置本地的隔天自動視為空", async () => {
  await appendTurn({ at: 1, said: "今天的話", reply: "今天的回答" });
  jest.setSystemTime(new Date("2026-08-08T00:01:00+08:00"));

  await expect(loadToday()).resolves.toEqual([]);
});

test("登出會清空當天紀錄", async () => {
  await appendTurn({ at: 1, said: "要清掉", reply: "好" });
  await clearToday();

  await expect(loadToday()).resolves.toEqual([]);
  expect(storage.removeItem).toHaveBeenCalledWith("kinsun.todayLog.v1");
});

test("損壞的本機資料不會擋住對講機", async () => {
  stored = "不是 JSON";
  await expect(loadToday()).resolves.toEqual([]);
});
