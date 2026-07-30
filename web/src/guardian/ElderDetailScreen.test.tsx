/** 長輩詳情：健康報告、每日摘要、行程摘要、代辦帳密、家屬邀請碼。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { ElderDetailScreen } from "./ElderDetailScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

/** 依請求路徑回不同的資料——這一頁一次打三支端點。 */
function mockByPath(map: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((path: string) => {
      const key = Object.keys(map).find((k) => path.includes(k));
      return Promise.resolve({
        status: 200,
        json: async () => envelope(key ? map[key] : null),
      });
    }),
  );
}

function renderDetail() {
  localStorage.setItem(
    "kinsun_web_session_guardian",
    JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
  );
  return render(
    <GuardianSession.Provider>
      <ElderDetailScreen elderId="e1" elderName="王阿嬤" onManageSchedules={vi.fn()} />
    </GuardianSession.Provider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("ElderDetailScreen", () => {
  it("沒有危急事件時說一切平安，而不是留白", async () => {
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [],
    });
    renderDetail();
    expect(await screen.findByText("沒有危急事件，一切平安。")).toBeInTheDocument();
  });

  it("有危急事件時逐筆列出，含分級與原話", async () => {
    mockByPath({
      "health-report": {
        risk_events: [{ tier: 2, reason: "說胸口悶", created_at: 1754000000 }],
        reminders: [{ kind: "medication", content: "吃藥", created_at: 1754000000 }],
      },
      "daily-summaries": [],
      schedules: [],
    });
    renderDetail();
    expect(await screen.findByText(/需留意/)).toBeInTheDocument();
    expect(screen.getByText(/說胸口悶/)).toBeInTheDocument();
    expect(screen.getByText("近 30 天提醒 1 則")).toBeInTheDocument();
  });

  it("列出每日摘要", async () => {
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [{ date: "2026-07-29", content: "今天心情不錯", created_at: 1754000000 }],
      schedules: [],
    });
    renderDetail();
    expect(await screen.findByText("2026-07-29")).toBeInTheDocument();
    expect(screen.getByText("今天心情不錯")).toBeInTheDocument();
  });

  it("列出行程摘要，並標出長輩自己交代的那些", async () => {
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [
        {
          group_id: "g1",
          kind: "custom",
          title: "散步",
          created_by: "elder",
          event_at: null,
          occurrences: [
            { schedule_id: "s1", repeat: "daily", time: "17:00", weekday: null, scheduled_at: null },
          ],
        },
      ],
    });
    renderDetail();
    expect(await screen.findByText("散步（每天 17:00）")).toBeInTheDocument();
    expect(screen.getByText("（長輩自己交代的）")).toBeInTheDocument();
  });

  it("帳密欄位沒填齊時儲存鈕不可按", async () => {
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [],
    });
    renderDetail();
    const save = await screen.findByRole("button", { name: "儲存帳密" });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("長輩手機號碼"), "0912345678");
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("密碼（至少 8 碼）"), "correct-horse-8");
    expect(save).toBeEnabled();
  });

  it("產生家屬邀請碼後顯示出來", async () => {
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [],
      "guardian-invites": { invite_code: "XY99" },
    });
    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "產生家屬邀請碼" }));
    expect(await screen.findByText("XY99")).toBeInTheDocument();
  });
});
