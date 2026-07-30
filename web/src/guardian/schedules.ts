/**
 * 行程頁的輸入組裝與顯示（D-76 P3）：把畫面上的欄位換成 API 要的 occurrences。
 *
 * 抽出來不放畫面裡的理由：三種類型各有一套「怎麼問時間」的規則，混進 JSX 會讓
 * 那一頁再也讀不懂；而且這裡是純函式，可以直接測。
 */

import type { ScheduleGroup, ScheduleInput } from "kinsun-shared/types";

/** 用藥時段字典：值與後端一致，四個時段只是預設，家屬也能直接填時刻。 */
export const SLOTS = [
  { value: "morning", label: "早上" },
  { value: "noon", label: "中午" },
  { value: "evening", label: "晚上" },
  { value: "bedtime", label: "睡前" },
] as const;

/** 前端顯示用的四時段預設鐘點；後端另有一份（家屬改過的以後端為準）。 */
const SLOT_HOURS: Record<string, string> = {
  morning: "08:00",
  noon: "12:00",
  evening: "18:00",
  bedtime: "21:00",
};

export const KIND_OPTIONS = [
  { value: "medication", label: "吃藥" },
  { value: "appointment", label: "回診" },
  { value: "custom", label: "其他" },
] as const;

const WEEKDAYS = "一二三四五六日";
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

type Built = Pick<ScheduleInput, "occurrences" | "event_date" | "event_time">;

/**
 * 把畫面欄位換成 API 的 occurrences。看不懂就回 null，讓畫面顯示提示而不是送出壞資料。
 *
 * 回診固定產生兩個鬧鐘（前一天＋當天）——這是 D-76 保留的既有行為，日期由後端
 * 依 APPOINTMENT_REMINDER_HOUR 決定鐘點，故這裡送的是「哪一天」而非「幾點提醒」。
 */
export function toOccurrences(
  kind: ScheduleGroup["kind"],
  input: { slots: string[]; when: string },
): Built | null {
  const when = input.when.trim();
  if (kind === "medication") {
    if (when) {
      return TIME_RE.test(when) ? { occurrences: [{ repeat: "daily", time: when }] } : null;
    }
    if (input.slots.length === 0) {
      return null;
    }
    return {
      occurrences: input.slots.map((slot) => ({ repeat: "daily", time: SLOT_HOURS[slot] })),
    };
  }
  if (kind === "appointment") {
    const [date, time = ""] = when.split(/\s+/);
    if (!DATE_RE.test(date ?? "") || (time && !TIME_RE.test(time))) {
      return null;
    }
    const day = new Date(`${date}T00:00:00`);
    const before = new Date(day.getTime() - 86400000);
    return {
      occurrences: [
        { repeat: "once", date: isoDate(before), time: "08:00" },
        { repeat: "once", date, time: "08:00" },
      ],
      event_date: date,
      event_time: time,
    };
  }
  return customOccurrences(when);
}

function customOccurrences(when: string): Built | null {
  const [head, tail] = when.split(/\s+/);
  if (!head || !tail || !TIME_RE.test(tail)) {
    return null;
  }
  if (head === "每天") {
    return { occurrences: [{ repeat: "daily", time: tail }] };
  }
  if (head.startsWith("每週") && head.length === 3) {
    const weekday = WEEKDAYS.indexOf(head[2]);
    return weekday < 0 ? null : { occurrences: [{ repeat: "weekly", time: tail, weekday }] };
  }
  return DATE_RE.test(head) ? { occurrences: [{ repeat: "once", date: head, time: tail }] } : null;
}

/**
 * 把 Date 格式化成 `YYYY-MM-DD`。
 *
 * ⚠️ **用本地日期分量，不可用 `toISOString()`**：這裡拿到的 Date 是用
 * `new Date("2026-08-05T00:00:00")` 依**本地時區**解析出來的，而 `toISOString()`
 * 轉的是 **UTC**。在 UTC+8（本專案使用者所在時區），本地午夜是前一天的 16:00Z，
 * 於是「回診前一天」會算成前兩天——提醒提早兩天響，長輩白跑一趟。
 *
 * 這個 bug 自 2026-07-25 存在於 `app/src/lib/schedules.ts`，因為它**只在 UTC 以東
 * 的時區發作**（UTC 與美洲都算得對），而且從來沒有測試涵蓋。
 */
function isoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function slotLabelForTime(time: string): string {
  const hour = Number(time.slice(0, 2));
  if (hour < 11) return "早上";
  if (hour < 15) return "中午";
  if (hour < 20) return "晚上";
  return "睡前";
}

/** 清單上那一行字。與後端 LINE 選單的講法保持一致，家屬兩邊看到的才是同一件事。 */
export function describeGroup(group: ScheduleGroup): string {
  const first = group.occurrences[0];
  if (group.kind === "medication") {
    const labels = group.occurrences
      .filter((o) => o.time)
      .map((o) => slotLabelForTime(o.time))
      .join("、");
    return `${group.title}（${labels}）`;
  }
  if (group.kind === "appointment" && group.event_at !== null) {
    const event = new Date(group.event_at * 1000);
    const stamp =
      event.getHours() || event.getMinutes()
        ? `${isoDate(event)} ${pad(event.getHours())}:${pad(event.getMinutes())}`
        : isoDate(event);
    return `${group.title}（${stamp}）`;
  }
  if (!first) {
    return group.title;
  }
  if (first.repeat === "daily") {
    return `${group.title}（每天 ${first.time}）`;
  }
  if (first.repeat === "weekly") {
    const weekday = first.weekday === null ? "" : WEEKDAYS[first.weekday];
    return `${group.title}（每週${weekday} ${first.time}）`;
  }
  const at = first.scheduled_at === null ? null : new Date(first.scheduled_at * 1000);
  return at
    ? `${group.title}（${isoDate(at)} ${pad(at.getHours())}:${pad(at.getMinutes())}）`
    : group.title;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}
