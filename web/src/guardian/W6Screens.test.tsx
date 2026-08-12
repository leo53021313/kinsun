/**
 * W6 兩支家屬端新畫面：每日摘要與改回診時間。
 *
 * ⚠️ 兩支都只用**現有 API**，不等後端。真正的重點是那幾個容易寫反的方向：摘要清單
 * 由新到舊、兩顆箭頭的停用條件、以及回診「存檔／刪除後要回上一頁」。
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { DailySummaryScreen } from "./DailySummaryScreen";
import { EditAppointmentScreen } from "./EditAppointmentScreen";
import { buildShareText, formatAppointmentWhen } from "./guardianFormat";

const api = vi.hoisted(() => ({
  listDailySummaries: vi.fn(),
  listSchedules: vi.fn(),
  updateSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
}));
vi.mock("./api", () => api);

const SESSION_KEY = "kinsun_web_session_guardian";

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(
    SESSION_KEY,
    JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
  );
  Object.values(api).forEach((fn) => fn.mockReset());
});

afterEach(() => vi.restoreAllMocks());

function renderIn(node: React.ReactNode) {
  return render(<GuardianSession.Provider>{node}</GuardianSession.Provider>);
}

describe("每日摘要", () => {
  // API 由新到舊排序。
  const SUMMARIES = [
    { date: "2026-08-08", content: "今天心情不錯，吃了兩餐。", created_at: 2 },
    { date: "2026-08-07", content: "說膝蓋有點痠。", created_at: 1 },
  ];

  it("預設顯示最新一天，最新那天的右箭頭停用", async () => {
    api.listDailySummaries.mockResolvedValue(SUMMARIES);
    renderIn(<DailySummaryScreen elderId="e1" />);

    expect(await screen.findByText("2026-08-08")).toBeInTheDocument();
    expect(screen.getByText("今天心情不錯，吃了兩餐。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "看後一天" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "看前一天" })).not.toBeDisabled();
  });

  it("往前一天看得到舊的那則，最舊那天左箭頭停用", async () => {
    // ⚠️ 方向很容易寫反：清單由新到舊，「前一天」是 index + 1。
    api.listDailySummaries.mockResolvedValue(SUMMARIES);
    renderIn(<DailySummaryScreen elderId="e1" />);
    await screen.findByText("2026-08-08");

    await userEvent.click(screen.getByRole("button", { name: "看前一天" }));
    expect(screen.getByText("2026-08-07")).toBeInTheDocument();
    expect(screen.getByText("說膝蓋有點痠。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "看前一天" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "看後一天" })).not.toBeDisabled();
  });

  it("免責聲明一定在：這是阿白整理的，不是長輩原話", async () => {
    api.listDailySummaries.mockResolvedValue(SUMMARIES);
    renderIn(<DailySummaryScreen elderId="e1" />);
    expect(
      await screen.findByText("這是阿白整理的摘要，不是長輩的原話。"),
    ).toBeInTheDocument();
  });

  it("有系統分享面板就用它", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, share });
    api.listDailySummaries.mockResolvedValue(SUMMARIES);
    renderIn(<DailySummaryScreen elderId="e1" />);
    await screen.findByText("2026-08-08");

    await userEvent.click(screen.getByRole("button", { name: "傳這份摘要給家人" }));
    expect(share).toHaveBeenCalledWith({ text: buildShareText(SUMMARIES[0]) });
    vi.unstubAllGlobals();
  });

  it("桌機沒有分享面板時退回複製，不是丟一個「不支援」給家屬", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    api.listDailySummaries.mockResolvedValue(SUMMARIES);
    renderIn(<DailySummaryScreen elderId="e1" />);
    await screen.findByText("2026-08-08");

    await userEvent.click(screen.getByRole("button", { name: "傳這份摘要給家人" }));
    expect(writeText).toHaveBeenCalledWith(buildShareText(SUMMARIES[0]));
    expect(await screen.findByRole("status")).toHaveTextContent("摘要已複製");
    vi.unstubAllGlobals();
  });

  it("還沒有摘要時說明原因，不是空白畫面", async () => {
    api.listDailySummaries.mockResolvedValue([]);
    renderIn(<DailySummaryScreen elderId="e1" />);
    expect(await screen.findByText(/還沒有摘要/)).toBeInTheDocument();
  });

  it("讀不到時給「再試一次」，按了會重打", async () => {
    api.listDailySummaries.mockRejectedValueOnce(new Error("boom"));
    renderIn(<DailySummaryScreen elderId="e1" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    api.listDailySummaries.mockResolvedValueOnce(SUMMARIES);
    await userEvent.click(screen.getByRole("button", { name: "再試一次" }));
    expect(await screen.findByText("2026-08-08")).toBeInTheDocument();
  });
});

describe("改回診時間", () => {
  const GROUP = {
    group_id: "g1",
    kind: "appointment" as const,
    title: "心臟科回診",
    created_by: "guardian" as const,
    // 2026-08-19 10:30（本地時區）
    event_at: Math.floor(new Date(2026, 7, 19, 10, 30).getTime() / 1000),
    occurrences: [],
  };

  it("預填現有的日期與時間", async () => {
    api.listSchedules.mockResolvedValue([GROUP]);
    renderIn(<EditAppointmentScreen elderId="e1" scheduleId="g1" onDone={vi.fn()} />);
    expect(await screen.findByDisplayValue("2026-08-19 10:30")).toBeInTheDocument();
  });

  it("存得起來，成功後回上一頁", async () => {
    api.listSchedules.mockResolvedValue([GROUP]);
    api.updateSchedule.mockResolvedValue(undefined);
    const onDone = vi.fn();
    renderIn(<EditAppointmentScreen elderId="e1" scheduleId="g1" onDone={onDone} />);
    const input = await screen.findByDisplayValue("2026-08-19 10:30");

    await userEvent.clear(input);
    await userEvent.type(input, "2026-08-20 14:00");
    await userEvent.click(screen.getByRole("button", { name: "存起來" }));

    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    const [elderId, groupId, body] = api.updateSchedule.mock.calls[0];
    expect(elderId).toBe("e1");
    expect(groupId).toBe("g1");
    expect(body).toMatchObject({ kind: "appointment", title: "心臟科回診" });
  });

  it("時間格式不對時先擋在前端，不必往返一趟", async () => {
    api.listSchedules.mockResolvedValue([GROUP]);
    renderIn(<EditAppointmentScreen elderId="e1" scheduleId="g1" onDone={vi.fn()} />);
    const input = await screen.findByDisplayValue("2026-08-19 10:30");

    await userEvent.clear(input);
    await userEvent.type(input, "下週三");
    await userEvent.click(screen.getByRole("button", { name: "存起來" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("請用「西元年-月-日");
    expect(api.updateSchedule).not.toHaveBeenCalled();
  });

  it("刪除要二次確認，且不用會鎖住整個分頁的 window.confirm", async () => {
    // 雙欄同時存在時，`window.confirm` 會讓另一欄連按都按不了。
    const confirmSpy = vi.spyOn(window, "confirm");
    api.listSchedules.mockResolvedValue([GROUP]);
    api.deleteSchedule.mockResolvedValue(undefined);
    const onDone = vi.fn();
    renderIn(<EditAppointmentScreen elderId="e1" scheduleId="g1" onDone={onDone} />);
    await screen.findByDisplayValue("2026-08-19 10:30");

    await userEvent.click(screen.getByRole("button", { name: "刪除這個行程" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("確定要刪除「心臟科回診」嗎？");
    expect(api.deleteSchedule).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "刪除" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(api.deleteSchedule).toHaveBeenCalledWith("e1", "g1", "tok");
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("確認列可以取消，取消後不會刪", async () => {
    api.listSchedules.mockResolvedValue([GROUP]);
    renderIn(<EditAppointmentScreen elderId="e1" scheduleId="g1" onDone={vi.fn()} />);
    await screen.findByDisplayValue("2026-08-19 10:30");

    await userEvent.click(screen.getByRole("button", { name: "刪除這個行程" }));
    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(api.deleteSchedule).not.toHaveBeenCalled();
  });

  it("找不到那筆行程時說清楚，不是停在空表單", async () => {
    api.listSchedules.mockResolvedValue([]);
    renderIn(<EditAppointmentScreen elderId="e1" scheduleId="g1" onDone={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("找不到這筆回診行程");
  });

  it("交付稿畫的「誰帶長輩去」與「讓阿白告訴長輩」刻意不做", async () => {
    // `ScheduleInput` 沒有 `driver` 與 `notify_elder`，後端也沒有。畫上去只會送出
    // 後端收不到的欄位，或更糟——讓家屬以為長輩會被告知而其實不會。
    api.listSchedules.mockResolvedValue([GROUP]);
    renderIn(<EditAppointmentScreen elderId="e1" scheduleId="g1" onDone={vi.fn()} />);
    await screen.findByDisplayValue("2026-08-19 10:30");
    expect(screen.queryByText(/誰帶長輩去/)).not.toBeInTheDocument();
    expect(screen.queryByText(/讓阿白告訴長輩/)).not.toBeInTheDocument();
  });
});

describe("格式化", () => {
  it("整點零分只顯示日期——後端對「還沒約時間」的回診就是存 00:00", () => {
    const midnight = Math.floor(new Date(2026, 7, 19, 0, 0).getTime() / 1000);
    expect(formatAppointmentWhen(midnight)).toBe("2026-08-19");
  });

  it("沒有時刻時回空字串", () => {
    expect(formatAppointmentWhen(null)).toBe("");
  });

  it("分享文字標明來源是服務（金孫），不是角色", () => {
    const text = buildShareText({ date: "2026-08-08", content: "還不錯。", created_at: 1 });
    expect(text).toContain("2026-08-08 的摘要");
    expect(text).toContain("還不錯。");
    expect(text).toContain("（由金孫產生）");
  });
});
