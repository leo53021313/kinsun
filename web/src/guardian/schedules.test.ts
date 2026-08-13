/**
 * 排程輸入組裝與描述（自 app/src/lib/schedules.ts 原樣搬移）。
 *
 * App 端沒有替它寫過測試，搬過來時補上——三種類型各有一套「怎麼問時間」的規則，
 * 而使用者打錯格式時唯一的回饋是「還沒填提醒時間」，看不出是哪裡不對。
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

  it("自己填時間會蓋過時段", () => {
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
    //
    // ⚠️ **這招只在 Node runner 有效**：它的辨別力依賴 Node 執行期重讀
    // `process.env.TZ`（已在 Node 24 驗證成立）。若日後這個專案改用 vitest
    // browser mode 跑測試，`process.env.TZ` 不存在也不會生效，這條測試會安靜地
    // 退化成依賴 ambient 時區——不報錯、不變紅，只是失去辨別力，換 runner 時
    // 要重新驗證。
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

  describe("時區", () => {
    // ⚠️ 這條守的是 describeGroup 的回診分支也共用 isoDate：時分用 event.getHours()
    // ／getMinutes()（本地時間），日期若還用 toISOString()（UTC）就會兩者不一致
    // ——凡是台北時間 00:00～07:59 的回診，家屬看到的日期本來就會少一天。這是
    // 修 toOccurrences 的「前一天」bug 時一併修掉的第二個既有 bug，之前沒有測試
    // 釘住。同樣用 vi.stubEnv 明確釘住 TZ，不依賴執行機器的 ambient 時區。
    afterEach(() => vi.unstubAllEnvs());

    it("回診顯示的日期依本地時間，不是 UTC——台北時間 07:00 的回診不會顯示成前一天", () => {
      vi.stubEnv("TZ", "Asia/Taipei");
      // 2026-08-05 07:00 台北時間（UTC+8）＝ 2026-08-04 23:00 UTC——用 UTC 取日期
      // 會顯示成前一天。用 Date.UTC 明確以 UTC 分量組出這個 epoch，避免測試本身
      // 又踩到「用本地時間解析字串」這個同一類地雷。
      const event_at = Date.UTC(2026, 7, 4, 23, 0, 0) / 1000;
      const text = describeGroup(
        group({ kind: "appointment", title: "心臟科回診", event_at }),
      );
      expect(text).toBe("心臟科回診（2026-08-05 07:00）");
    });
  });
});
