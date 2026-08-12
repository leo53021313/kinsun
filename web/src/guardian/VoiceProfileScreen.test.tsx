/** 家屬錄音畫面：稿子來源、已設定狀態、同意欄預設值、送不出去的條件、讀取失敗。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { VoiceProfileScreen } from "./VoiceProfileScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

const SCRIPT = {
  script: "阿嬤您好，今天過得好嗎。",
  tips: ["請在安靜的地方錄音。"],
  rationale: {},
};

/**
 * 依路徑分派回應。稿子那支固定成功，狀態那支由呼叫端決定——兩支是併行發出的，
 * 用同一個回應會讓「稿子讀到了但狀態讀不到」這種真實情形測不出來。
 */
function stubApi(status: { code?: number; body?: unknown }) {
  const spy = vi.fn().mockImplementation((path: string) => {
    if (String(path).includes("voice-profile-script")) {
      return Promise.resolve({ status: 200, json: async () => envelope(SCRIPT) });
    }
    const code = status.code ?? 200;
    return Promise.resolve({
      status: code,
      json: async () =>
        code === 200
          ? envelope(status.body)
          : { success: false, data: null, error: { code: "server_error", message: "壞了" }, meta: null },
    });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

/** jsdom 沒有 mediaDevices；不塞的話 probeMicrophone 會回 unsupported 並顯示紅字。 */
function stubMicrophone() {
  vi.stubGlobal("navigator", {
    mediaDevices: {
      getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
    },
  });
}

function renderScreen() {
  // 鍵名逐字取自 `session/storage.ts::KEYS`。打錯的話 session 是 null、同意欄
  // 會是空的，而那條測試會以「預設值沒帶進去」的形狀失敗，很難聯想到是鍵名。
  localStorage.setItem(
    "kinsun_web_session_guardian",
    JSON.stringify({ role: "guardian", token: "tok", display_name: "女兒" }),
  );
  return render(
    <GuardianSession.Provider>
      <VoiceProfileScreen elderId="e1" elderName="王阿嬤" />
    </GuardianSession.Provider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  stubMicrophone();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("VoiceProfileScreen", () => {
  it("顯示伺服器下發的稿子與注意事項，不是前端寫死的", async () => {
    stubApi({ body: { elder_id: "e1", has_profile: false } });
    renderScreen();
    expect(await screen.findByText(/阿嬤您好，今天過得好嗎/)).toBeInTheDocument();
    expect(screen.getByText(/請在安靜的地方錄音/)).toBeInTheDocument();
  });

  it("已設定過時顯示是誰的聲音，並提供改回預設", async () => {
    stubApi({
      body: { elder_id: "e1", has_profile: true, consented_by: "女兒", granted_at: 1754956800 },
    });
    renderScreen();
    expect(await screen.findByText(/目前使用 女兒 的聲音/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /改回預設聲音/ })).toBeInTheDocument();
  });

  it("同意欄預設帶登入家屬的名字", async () => {
    stubApi({ body: { elder_id: "e1", has_profile: false } });
    renderScreen();
    expect(await screen.findByDisplayValue("女兒")).toBeInTheDocument();
  });

  it("還沒錄音時送不出去", async () => {
    stubApi({ body: { elder_id: "e1", has_profile: false } });
    renderScreen();
    await screen.findByText(/阿嬤您好/);
    expect(screen.getByRole("button", { name: /設定成這個聲音/ })).toBeDisabled();
  });

  it("只勾同意、沒有錄音，仍然送不出去", async () => {
    stubApi({ body: { elder_id: "e1", has_profile: false } });
    renderScreen();
    await screen.findByText(/阿嬤您好/);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: /設定成這個聲音/ })).toBeDisabled();
  });

  it("讀不到目前設定時講出來，不假裝成沒設定過", async () => {
    // ⚠️ 靜默當成「沒設定過」的話，家屬會以為聲音沒設定成功、重錄一次把原本
    // 好好的那一份覆蓋掉。
    stubApi({ code: 500 });
    renderScreen();
    expect(await screen.findByText(/讀不到目前的設定/)).toBeInTheDocument();
  });
});
