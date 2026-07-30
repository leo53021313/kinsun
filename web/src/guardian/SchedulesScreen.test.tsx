/** 排程管理：三種類型 × 三種重複的新增、修改、刪除。 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { SchedulesScreen } from "./SchedulesScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

const WALK = {
  group_id: "g1",
  kind: "custom",
  title: "散步",
  created_by: "guardian",
  event_at: null,
  occurrences: [
    { schedule_id: "s1", repeat: "daily", time: "17:00", weekday: null, scheduled_at: null },
  ],
};

function renderScreen(fetchImpl: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchImpl);
  localStorage.setItem(
    "kinsun_web_session_guardian",
    JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
  );
  return render(
    <GuardianSession.Provider>
      <SchedulesScreen elderId="e1" />
    </GuardianSession.Provider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("SchedulesScreen", () => {
  it("列出既有的行程", async () => {
    renderScreen(vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([WALK]) }));
    expect(await screen.findByText("散步（每天 17:00）")).toBeInTheDocument();
  });

  it("沒有行程時顯示引導文字", async () => {
    renderScreen(vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([]) }));
    expect(await screen.findByText("還沒有任何提醒，從下方新增第一筆。")).toBeInTheDocument();
  });

  it("切換類型會換掉時間欄位的問法", async () => {
    renderScreen(vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([]) }));
    await screen.findByText("還沒有任何提醒，從下方新增第一筆。");
    // 預設是用藥：顯示時段複選
    expect(screen.getByRole("checkbox", { name: "早上" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "回診" }));
    expect(screen.queryByRole("checkbox", { name: "早上" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("回診日期")).toBeInTheDocument();
  });

  it("新增用藥：選時段後送出正確的 occurrences", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([]) })
      .mockResolvedValueOnce({ status: 201, json: async () => envelope(WALK) })
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([WALK]) });
    renderScreen(fetchImpl);
    await screen.findByText("還沒有任何提醒，從下方新增第一筆。");
    await userEvent.type(screen.getByLabelText("提醒內容"), "降血壓藥");
    await userEvent.click(screen.getByRole("checkbox", { name: "早上" }));
    await userEvent.click(screen.getByRole("button", { name: "新增" }));
    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(3));
    const body = JSON.parse(fetchImpl.mock.calls[1][1].body as string);
    expect(body).toEqual({
      kind: "medication",
      title: "降血壓藥",
      occurrences: [{ repeat: "daily", time: "08:00" }],
    });
  });

  it("時間格式看不懂時擋下來，不打後端", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue({ status: 200, json: async () => envelope([]) });
    renderScreen(fetchImpl);
    await screen.findByText("還沒有任何提醒，從下方新增第一筆。");
    await userEvent.click(screen.getByRole("radio", { name: "其他" }));
    await userEvent.type(screen.getByLabelText("提醒內容"), "散步");
    await userEvent.type(screen.getByLabelText("提醒時間"), "每月三號 15:00");
    fetchImpl.mockClear();
    await userEvent.click(screen.getByRole("button", { name: "新增" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "請填寫提醒時間，格式請照欄位下方的範例。",
    );
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("按編輯會把標題帶進表單，並提示要重填時間", async () => {
    renderScreen(vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([WALK]) }));
    await userEvent.click(await screen.findByRole("button", { name: "編輯" }));
    expect(screen.getByLabelText("提醒內容")).toHaveValue("散步");
    expect(screen.getByRole("alert")).toHaveTextContent("修改後請重新填一次提醒時間。");
    expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
  });

  it("刪除要先確認，取消就不打後端", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([WALK]) });
    renderScreen(fetchImpl);
    await userEvent.click(await screen.findByRole("button", { name: "刪除" }));
    expect(screen.getByText("確定要刪除「散步」嗎？")).toBeInTheDocument();
    // ⚠️ 這一句是關鍵：只驗證「按取消後沒有新呼叫」守不住「按刪除鍵當下就已經
    // 送出 DELETE」這種錯——mockClear() 會把那次呼叫洗掉，讓下面的斷言誤判通過。
    // 開確認列的當下必須還沒打過任何 DELETE。
    expect(
      fetchImpl.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "DELETE"),
    ).toBe(false);
    fetchImpl.mockClear();
    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("確認刪除後才打 DELETE", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([WALK]) })
      .mockResolvedValueOnce({ status: 204, json: async () => ({}) })
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([]) });
    renderScreen(fetchImpl);
    await userEvent.click(await screen.findByRole("button", { name: "刪除" }));
    await userEvent.click(screen.getByRole("button", { name: "確定刪除" }));
    await waitFor(() => {
      expect(fetchImpl.mock.calls[1][1].method).toBe("DELETE");
      expect(fetchImpl.mock.calls[1][0]).toBe("/api/v1/elders/e1/schedules/g1");
    });
  });
});
