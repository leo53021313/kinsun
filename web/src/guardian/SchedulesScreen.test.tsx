/** 排程管理：用藥／回診／自訂三種提醒類型共用的新增、修改、刪除（各類型可用的重複方式不同，非三三對應）。 */

import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStageEvent } from "@/notify/bus";
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

const APPT = {
  group_id: "g2",
  kind: "appointment",
  title: "心臟科回診",
  created_by: "guardian",
  event_at: 1754268000,
  occurrences: [
    { schedule_id: "s2", repeat: "once", time: "08:00", weekday: null, scheduled_at: 1754268000 },
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
      <SchedulesScreen elderId="e1" elderName="王阿嬤" />
    </GuardianSession.Provider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("SchedulesScreen", () => {
  // 家屬管兩位以上長輩時，這一頁若只寫「行程管理」，畫面上沒有任何字告訴他正在
  // 編誰的提醒——而相鄰的 ElderDetailScreen 是刻意把 elderName 傳進去當標題的。
  it("標題帶上長輩的稱呼，家屬才知道正在編誰的提醒", async () => {
    renderScreen(vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([]) }));
    expect(await screen.findByRole("heading", { name: "王阿嬤的行程管理" })).toBeInTheDocument();
  });

  it("列出既有的行程", async () => {
    renderScreen(vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([WALK]) }));
    expect(await screen.findByText("散步（每天 17:00）")).toBeInTheDocument();
  });

  it("沒有行程時顯示引導文字", async () => {
    renderScreen(vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([]) }));
    expect(await screen.findByText("還沒有任何提醒，從下方新增第一筆。")).toBeInTheDocument();
  });

  it("載入中會先顯示載入中，不會先閃過『還沒有任何提醒』", async () => {
    // ⚠️ 用手動控制的 promise，不是 mockResolvedValue：後者在同一個 microtask
    // 就解出結果，測試永遠只看得到「解完之後」那一瞬間，看不出畫面在「還沒解完
    // 之前」顯示的是什麼——這正是 P1 抓過的同一種假測試手法。
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    const fetchImpl = vi.fn().mockReturnValue(pending);
    renderScreen(fetchImpl);
    expect(await screen.findByText("載入中…")).toBeInTheDocument();
    expect(screen.queryByText("還沒有任何提醒，從下方新增第一筆。")).not.toBeInTheDocument();
    resolveFetch({ status: 200, json: async () => envelope([]) });
    expect(await screen.findByText("還沒有任何提醒，從下方新增第一筆。")).toBeInTheDocument();
  });

  // ⚠️ 同一份清單（`listSchedules`）在 `ElderDetailScreen` 早就用 `groupsError`
  // 正確降級了，這裡卻讓 `groups` 留在 null——畫面同時顯示「載入失敗，請稍後再試。」
  // 與「載入中…」兩句互相矛盾的話。家屬會照著「載入中」等下去，而且永遠等不到：
  // 畫面上沒有重試鈕，唯一的復原方式是按返回再進來一次。
  it("載入失敗時只說載入失敗，不可同時還說「載入中…」", async () => {
    renderScreen(
      vi.fn().mockResolvedValue({
        status: 500,
        json: async () => ({
          success: false,
          data: null,
          error: { code: "server_error", message: "系統忙碌，請稍後再試" },
          meta: null,
        }),
      }),
    );
    expect(await screen.findByText("載入失敗，請稍後再試。")).toBeInTheDocument();
    expect(screen.queryByText("載入中…")).not.toBeInTheDocument();
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
    // ⚠️ status 而非 alert：按「編輯」是一個**成功**的操作，這句話是操作指示、
    // 不是錯誤。掛 role="alert" 會讓螢幕報讀軟體當警示打斷朗讀，畫面上也會跳紅字。
    expect(screen.getByRole("status")).toHaveTextContent("修改後請重新填一次提醒時間。");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
  });

  it("按取消編輯回到新增模式時，重填提示要一併消失", async () => {
    renderScreen(vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([WALK]) }));
    await userEvent.click(await screen.findByRole("button", { name: "編輯" }));
    expect(screen.getByRole("status")).toHaveTextContent("修改後請重新填一次提醒時間。");
    await userEvent.click(screen.getByRole("button", { name: "取消編輯" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByLabelText("提醒內容")).toHaveValue("");
  });

  it("編輯後按更新：真的送出 PUT，且欄位對應被編輯那筆的類型", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([APPT]) })
      .mockResolvedValueOnce({ status: 200, json: async () => envelope(APPT) })
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([APPT]) });
    renderScreen(fetchImpl);
    await userEvent.click(await screen.findByRole("button", { name: "編輯" }));
    // 釘住 setKind(group.kind)：編輯「回診」這筆時應該立刻換成回診日期欄，而不是
    // 停在用藥預設的時段複選——欄位跟正在編輯的類型對不上，家屬會填錯地方。
    expect(screen.getByLabelText("回診日期")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "早上" })).not.toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("提醒內容"));
    await userEvent.type(screen.getByLabelText("提醒內容"), "心臟科回診（改約）");
    await userEvent.type(screen.getByLabelText("回診日期"), "2026-08-10");
    await userEvent.click(screen.getByRole("button", { name: "更新" }));

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(3));
    expect(fetchImpl.mock.calls[1][1].method).toBe("PUT");
    expect(fetchImpl.mock.calls[1][0]).toBe("/api/v1/elders/e1/schedules/g2");
    const body = JSON.parse(fetchImpl.mock.calls[1][1].body as string);
    expect(body).toEqual({
      kind: "appointment",
      title: "心臟科回診（改約）",
      occurrences: [
        { repeat: "once", date: "2026-08-09", time: "08:00" },
        { repeat: "once", date: "2026-08-10", time: "08:00" },
      ],
      event_date: "2026-08-10",
      event_time: "",
    });
  });

  // ⚠️ 隧道抖動回的 502 HTML 不是 JSON；shared/client.ts 的 json() 解析失敗會
  // 自造 `http_502` / `HTTP 502`，不可把這種英文字面值照實顯示給家屬看。
  it("新增時後端回非 JSON（如隧道抖動的 502），顯示繁中的儲存失敗，不印出 HTTP 502", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([]) })
      .mockResolvedValueOnce({
        status: 502,
        json: async () => {
          throw new SyntaxError("Unexpected token '<'");
        },
      });
    renderScreen(fetchImpl);
    await screen.findByText("還沒有任何提醒，從下方新增第一筆。");
    await userEvent.type(screen.getByLabelText("提醒內容"), "降血壓藥");
    await userEvent.click(screen.getByRole("checkbox", { name: "早上" }));
    await userEvent.click(screen.getByRole("button", { name: "新增" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("儲存失敗，請稍後再試。");
    expect(screen.queryByText(/HTTP 502/)).not.toBeInTheDocument();
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
    // 只驗證「沒打後端」不夠：確認列本身要真的關掉，否則使用者以為取消生效了，
    // 但那個唯一能反悔的按鈕其實還卡在畫面上（或者，更糟，卡在畫面上卻按不動）。
    expect(screen.queryByText("確定要刪除「散步」嗎？")).not.toBeInTheDocument();
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
    // 光打了 DELETE 不夠：清單要真的重新整理、被刪的那一列要從畫面上消失，
    // 不然家屬會看著同一列以為沒刪成功，再按一次刪除鍵。
    await waitFor(() =>
      expect(screen.queryByText("散步（每天 17:00）")).not.toBeInTheDocument(),
    );
  });

  // ⚠️ 這兩條守的是「跨欄連動」（notify/bus.ts）：家屬這頁寫入成功後，長輩欄不必
  // 等下一次輪詢（最多兩秒）就能立刻知道有新事情發生。用真正的 `useStageEvent`
  // （而非 mock `emitStageEvent`）掛一個訂閱者旁觀，較貼近實際跨欄的用法。
  it("新增排程成功後會發出 guardian-wrote 事件", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([]) })
      .mockResolvedValueOnce({ status: 201, json: async () => envelope(WALK) })
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([WALK]) });
    const { result } = renderHook(() => useStageEvent("guardian-wrote"));
    const before = result.current;
    renderScreen(fetchImpl);
    await screen.findByText("還沒有任何提醒，從下方新增第一筆。");
    await userEvent.type(screen.getByLabelText("提醒內容"), "散步");
    await userEvent.click(screen.getByRole("checkbox", { name: "早上" }));
    await userEvent.click(screen.getByRole("button", { name: "新增" }));
    await waitFor(() => expect(result.current).not.toBe(before));
  });

  it("刪除確認後也會發出 guardian-wrote 事件", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([WALK]) })
      .mockResolvedValueOnce({ status: 204, json: async () => ({}) })
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([]) });
    const { result } = renderHook(() => useStageEvent("guardian-wrote"));
    const before = result.current;
    renderScreen(fetchImpl);
    await userEvent.click(await screen.findByRole("button", { name: "刪除" }));
    await userEvent.click(screen.getByRole("button", { name: "確定刪除" }));
    await waitFor(() => expect(result.current).not.toBe(before));
  });
});
