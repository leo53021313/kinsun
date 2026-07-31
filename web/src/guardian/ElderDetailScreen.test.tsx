/** 長輩詳情：健康報告、每日摘要、行程摘要、代辦帳密、家屬邀請碼。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { ElderDetailScreen } from "./ElderDetailScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function failure(code: string, message: string) {
  return { success: false, data: null, error: { code, message }, meta: null };
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

/**
 * 依請求路徑回不同的狀態碼與內容——用來驗證三支端點其中一支失敗時，其餘兩支
 * 照常顯示，不是全部一起卡住（見「三支端點其中一支失敗」測試）。
 */
function mockMixedByPath(map: Record<string, { status: number; body: unknown }>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((path: string) => {
      const key = Object.keys(map).find((k) => path.includes(k));
      const entry = key ? map[key] : { status: 200, body: envelope(null) };
      return Promise.resolve({ status: entry.status, json: async () => entry.body });
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

  it("三支端點其中一支失敗時，其餘兩支照常顯示，失敗的那個區塊顯示錯誤而不是卡在載入中", async () => {
    mockMixedByPath({
      "health-report": { status: 500, body: failure("server_error", "系統忙碌，請稍後再試") },
      "daily-summaries": {
        status: 200,
        body: envelope([{ date: "2026-07-29", content: "今天心情不錯", created_at: 1754000000 }]),
      },
      schedules: {
        status: 200,
        body: envelope([
          {
            group_id: "g1",
            kind: "custom",
            title: "散步",
            created_by: "guardian",
            event_at: null,
            occurrences: [
              { schedule_id: "s1", repeat: "daily", time: "17:00", weekday: null, scheduled_at: null },
            ],
          },
        ]),
      },
    });
    renderDetail();
    expect(await screen.findByText("今天心情不錯")).toBeInTheDocument();
    expect(screen.getByText("散步（每天 17:00）")).toBeInTheDocument();
    expect(screen.getByText("載入失敗，請稍後再試。")).toBeInTheDocument();
    expect(screen.queryByText("載入中…")).not.toBeInTheDocument();
  });

  // ⚠️ 這兩條守的是「成功與失敗在畫面上必須長得不一樣」。原本兩者共用同一個
  // accountMessage 狀態、同一個裸 <p className="text-xs text-ink-soft">：家屬填了
  // 一組已被別的長輩佔用的手機號碼、後端回 409，那句灰色小字出現在跟「已設定完成」
  // 完全相同的位置與樣式，他會判定設好了，然後拿那組帳密去長輩端登入吃 401。
  it("代辦帳密成功時顯示成功訊息，且不是警示", async () => {
    mockMixedByPath({
      "health-report": { status: 200, body: envelope({ risk_events: [], reminders: [] }) },
      "daily-summaries": { status: 200, body: envelope([]) },
      schedules: { status: 200, body: envelope([]) },
      account: { status: 200, body: envelope({ elder_id: "e1" }) },
    });
    renderDetail();
    await userEvent.type(await screen.findByLabelText("長輩手機號碼"), "0912345678");
    await userEvent.type(screen.getByLabelText("密碼（至少 8 碼）"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "儲存帳密" }));
    expect(
      await screen.findByText(
        "已設定完成。長輩手機用這組號碼＋密碼登入一次就會一直記住。",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("代辦帳密失敗時走紅字警示，且不會同時出現成功訊息", async () => {
    mockMixedByPath({
      "health-report": { status: 200, body: envelope({ risk_events: [], reminders: [] }) },
      "daily-summaries": { status: 200, body: envelope([]) },
      schedules: { status: 200, body: envelope([]) },
      account: {
        status: 409,
        body: failure("phone_taken", "這個手機號碼已經幫另一位長輩註冊過了"),
      },
    });
    renderDetail();
    await userEvent.type(await screen.findByLabelText("長輩手機號碼"), "0912345678");
    await userEvent.type(screen.getByLabelText("密碼（至少 8 碼）"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "儲存帳密" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "這個手機號碼已經幫另一位長輩註冊過了",
    );
    expect(
      screen.queryByText("已設定完成。長輩手機用這組號碼＋密碼登入一次就會一直記住。"),
    ).not.toBeInTheDocument();
  });

  it("改動號碼或密碼時清掉上一次的結果訊息", async () => {
    // 舊的「已設定完成」掛在新輸入的號碼旁邊，家屬會以為新號碼也已經存好了。
    mockMixedByPath({
      "health-report": { status: 200, body: envelope({ risk_events: [], reminders: [] }) },
      "daily-summaries": { status: 200, body: envelope([]) },
      schedules: { status: 200, body: envelope([]) },
      account: { status: 200, body: envelope({ elder_id: "e1" }) },
    });
    renderDetail();
    await userEvent.type(await screen.findByLabelText("長輩手機號碼"), "0912345678");
    await userEvent.type(screen.getByLabelText("密碼（至少 8 碼）"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "儲存帳密" }));
    await screen.findByText("已設定完成。長輩手機用這組號碼＋密碼登入一次就會一直記住。");
    await userEvent.type(screen.getByLabelText("長輩手機號碼"), "9");
    expect(
      screen.queryByText("已設定完成。長輩手機用這組號碼＋密碼登入一次就會一直記住。"),
    ).not.toBeInTheDocument();
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

  it("產生邀請碼失敗後重試成功，舊的錯誤要一併消失", async () => {
    // 不清的話，頁面最上方掛著紅字「產生邀請碼失敗」，下方同時顯示一組有效的
    // 邀請碼——家屬不知道該相信哪一個。
    let inviteCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string) => {
        if (String(path).includes("guardian-invites")) {
          inviteCalls += 1;
          return Promise.resolve(
            inviteCalls === 1
              ? { status: 500, json: async () => failure("server_error", "系統忙碌，請稍後再試") }
              : { status: 201, json: async () => envelope({ invite_code: "XY99" }) },
          );
        }
        if (String(path).includes("health-report")) {
          return Promise.resolve({
            status: 200,
            json: async () => envelope({ risk_events: [], reminders: [] }),
          });
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "產生家屬邀請碼" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("產生邀請碼失敗");
    await userEvent.click(screen.getByRole("button", { name: "產生家屬邀請碼" }));
    expect(await screen.findByText("XY99")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // ⚠️ 綁定碼原本只活在 `HomeScreen` 的暫態 state：家屬建完長輩點進詳情頁再返回，
  // 碼就永久不見了（`GET /elders` 的回應裡沒有它），而詳情頁的「邀請其他家屬」發
  // 的是家屬邀請碼、不是長輩綁定碼。這也是 P3 的硬阻斷——P3 有三句錯誤訊息叫長輩
  // 「請家人重新產生一組」，而家屬端根本沒有重新產生的路徑，那三句是死路。
  describe("重新產生長輩綁定碼", () => {
    it("成功後顯示新的綁定碼", async () => {
      mockByPath({
        "health-report": { risk_events: [], reminders: [] },
        "daily-summaries": [],
        schedules: [],
        "device-bindings": { invite_code: "NEW789" },
      });
      renderDetail();
      await userEvent.click(
        await screen.findByRole("button", { name: "重新產生長輩綁定碼" }),
      );
      expect(await screen.findByText("NEW789")).toBeInTheDocument();
    });

    it("按下去之前就先講清楚後果：長輩手機上的金孫會被登出", async () => {
      // 這是一個不可逆的破壞性操作，畫面必須先講後果，別讓家屬誤按。
      mockByPath({
        "health-report": { risk_events: [], reminders: [] },
        "daily-summaries": [],
        schedules: [],
      });
      renderDetail();
      expect(
        await screen.findByText(
          "注意：一產生新碼，長輩目前手機上的金孫就會被登出，他要用新碼重綁一次才能" +
            "再跟金孫說話。只是想邀請另一位家屬看資料的話，請用下面的「產生家屬邀請碼」。",
        ),
      ).toBeInTheDocument();
    });

    it("失敗時就地顯示錯誤，不會安靜地什麼都沒發生", async () => {
      mockMixedByPath({
        "health-report": { status: 200, body: envelope({ risk_events: [], reminders: [] }) },
        "daily-summaries": { status: 200, body: envelope([]) },
        schedules: { status: 200, body: envelope([]) },
        "device-bindings": {
          status: 500,
          body: failure("server_error", "系統忙碌，請稍後再試"),
        },
      });
      renderDetail();
      await userEvent.click(
        await screen.findByRole("button", { name: "重新產生長輩綁定碼" }),
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "重新產生綁定碼失敗，請稍後再試。",
      );
    });
  });
});
