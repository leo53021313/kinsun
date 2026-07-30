/**
 * 排程輸入組裝與描述（自 app/src/lib/schedules.ts 原樣搬移）。
 *
 * App 端沒有替它寫過測試，搬過來時補上——三種類型各有一套「怎麼問時間」的規則，
 * 而使用者打錯格式時唯一的回饋是「請填寫提醒時間」，看不出是哪裡不對。
 */

import type { ScheduleGroup } from "kinsun-shared/types";
import { afterEach, describe, expect, it, vi } from "vitest";

import { describeGroup, toOccurrences } from "./schedules";

describe("toOccurrences：用藥", () => {
  it("選了時段就每個時段各一個鬧鐘", () => {
    expect(toOccurrences("medication", { slots: ["morning", "bedtime"], when: "" })).toEqual({
      occurrences: [
        { repeat: "daily", time: "08:00" },
        { repeat: "daily", time: "21:00" },
      ],
    });
  });

  it("直接指定時刻會蓋過時段", () => {
    expect(toOccurrences("medication", { slots: ["morning"], when: "07:30" })).toEqual({
      occurrences: [{ repeat: "daily", time: "07:30" }],
    });
  });

  it("時刻格式不對時回 null，讓畫面顯示提示而不是送出壞資料", () => {
    expect(toOccurrences("medication", { slots: [], when: "7:30" })).toBeNull();
    expect(toOccurrences("medication", { slots: [], when: "25:00" })).toBeNull();
  });

  it("什麼都沒填回 null", () => {
    expect(toOccurrences("medication", { slots: [], when: "" })).toBeNull();
  });
});

describe("toOccurrences：回診", () => {
  it("產生前一天與當天兩個鬧鐘，並記下看診時刻", () => {
    const built = toOccurrences("appointment", { slots: [], when: "2026-08-05 10:30" });
    expect(built).toEqual({
      occurrences: [
        { repeat: "once", date: "2026-08-04", time: "08:00" },
        { repeat: "once", date: "2026-08-05", time: "08:00" },
      ],
      event_date: "2026-08-05",
      event_time: "10:30",
    });
  });

  it("時刻可以省略", () => {
    const built = toOccurrences("appointment", { slots: [], when: "2026-08-05" });
    expect(built?.event_time).toBe("");
  });

  it("日期格式不對回 null", () => {
    expect(toOccurrences("appointment", { slots: [], when: "2026/08/05" })).toBeNull();
  });

  describe("時區", () => {
    // ⚠️ 這條守的是 isoDate 不可用 toISOString()：這個 bug 只在 UTC 以東的時區發作
    // （UTC 與美洲都算得對），在 UTC 跑的 CI 因此永遠看不到它。用 vi.stubEnv 明確
    // 釘住 TZ，讓這條測試不論在哪一台機器、哪個 CI 環境執行都有辨別力，不必依賴
    // 執行機器剛好被設成 Asia/Taipei（已用變異驗證證實：見報告）。
    afterEach(() => vi.unstubAllEnvs());

    it("回診的「前一天」在 UTC+8 也算得對", () => {
      vi.stubEnv("TZ", "Asia/Taipei");
      const built = toOccurrences("appointment", { slots: [], when: "2026-08-05" });
      expect(built?.occurrences[0].date).toBe("2026-08-04");
    });
  });
});

describe("toOccurrences：其他", () => {
  it("每天", () => {
    expect(toOccurrences("custom", { slots: [], when: "每天 17:00" })).toEqual({
      occurrences: [{ repeat: "daily", time: "17:00" }],
    });
  });

  it("每週三（星期一是 0）", () => {
    expect(toOccurrences("custom", { slots: [], when: "每週三 15:00" })).toEqual({
      occurrences: [{ repeat: "weekly", time: "15:00", weekday: 2 }],
    });
  });

  it("指定日期", () => {
    expect(toOccurrences("custom", { slots: [], when: "2026-08-05 09:00" })).toEqual({
      occurrences: [{ repeat: "once", date: "2026-08-05", time: "09:00" }],
    });
  });

  it("看不懂的講法回 null", () => {
    expect(toOccurrences("custom", { slots: [], when: "每月三號 15:00" })).toBeNull();
    expect(toOccurrences("custom", { slots: [], when: "每天" })).toBeNull();
  });
});

function group(overrides: Partial<ScheduleGroup>): ScheduleGroup {
  return {
    group_id: "g1",
    kind: "custom",
    title: "散步",
    created_by: "guardian",
    event_at: null,
    occurrences: [],
    ...overrides,
  };
}

describe("describeGroup", () => {
  it("用藥以時段講，不講時刻——家屬看的是「早上那顆」", () => {
    const text = describeGroup(
      group({
        kind: "medication",
        title: "降血壓藥",
        occurrences: [
          { schedule_id: "s1", repeat: "daily", time: "08:00", weekday: null, scheduled_at: null },
          { schedule_id: "s2", repeat: "daily", time: "21:00", weekday: null, scheduled_at: null },
        ],
      }),
    );
    expect(text).toBe("降血壓藥（早上、睡前）");
  });

  it("每天的自訂提醒講時刻", () => {
    const text = describeGroup(
      group({
        occurrences: [
          { schedule_id: "s1", repeat: "daily", time: "17:00", weekday: null, scheduled_at: null },
        ],
      }),
    );
    expect(text).toBe("散步（每天 17:00）");
  });

  it("每週的自訂提醒講星期幾", () => {
    const text = describeGroup(
      group({
        occurrences: [
          { schedule_id: "s1", repeat: "weekly", time: "15:00", weekday: 2, scheduled_at: null },
        ],
      }),
    );
    expect(text).toBe("散步（每週三 15:00）");
  });

  it("沒有任何鬧鐘時只講標題，不擲例外", () => {
    expect(describeGroup(group({ occurrences: [] }))).toBe("散步");
  });
});
