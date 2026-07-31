/** 長輩配對與重登。文案更白話、字更大是刻意的（適老化 ✅ D-48）。 */

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElderSession } from "@/session/contexts";

import { ElderApp } from "./ElderApp";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function failure(code: string, message: string) {
  return { success: false, data: null, error: { code, message }, meta: null };
}

function renderApp() {
  return render(
    <ElderSession.Provider>
      <ElderApp />
    </ElderSession.Provider>,
  );
}

/**
 * `talk/qrScanner.ts` 的真正實作需要相機與 wasm（見該檔測試 `qrScanner.test.ts`）；
 * 這裡整支模組換成假的，只留 `BindScreen` 呼叫端傳進來的 `onCode`／`onError`
 * 存起來，讓測試自己決定何時觸發——驗證的是 `BindScreen` 自己的邏輯（錯誤對應
 * 表、相機資源釋放時機），不是相機或 wasm 本身。
 *
 * ⚠️ 用 `vi.hoisted`：`vi.mock` 的 factory 會被提升到檔案最上方執行，若直接在
 * 這裡參照下方才宣告的一般 `let`／`const`，會踩到「宣告前就被讀取」的暫時性
 * 死區；`vi.hoisted` 保證這個物件在 factory 執行前就已經初始化完成。
 */
const scannerState = vi.hoisted(() => ({
  stop: vi.fn(),
  onCode: null as ((text: string) => void) | null,
  onError: null as ((reason: string) => void) | null,
}));

vi.mock("@/talk/qrScanner", () => ({
  createQrScanner: (options: {
    video: HTMLVideoElement;
    onCode: (text: string) => void;
    onError?: (reason: string) => void;
  }) => {
    scannerState.onCode = options.onCode;
    scannerState.onError = options.onError ?? null;
    return { stop: scannerState.stop };
  },
}));

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("navigator", { mediaDevices: undefined });
});
afterEach(() => {
  vi.unstubAllGlobals();
  scannerState.stop.mockClear();
  scannerState.onCode = null;
  scannerState.onError = null;
});

describe("長輩配對", () => {
  it("未登入時顯示配對畫面", () => {
    renderApp();
    expect(screen.getByText("掃描家人給的方塊圖，或輸入號碼")).toBeInTheDocument();
  });

  it("輸入綁定碼成功後離開配對畫面（對講機由 Task 8 接上）", async () => {
    // ⚠️ 修正 brief 缺陷：Step 1 給定的這條測試原本斷言綁定成功後會看到
    // 「按住說話」按鈕，但 Task 7 的檔案清單只有 BindScreen／LoginScreen／
    // ElderApp 三個檔案——對講機（talk 路由）要等 Task 8 才會接上真正的畫面；
    // 在那之前 `ElderApp` 的 `default` 分支（涵蓋 talk／notifications 兩個
    // 路由）一律顯示佔位文字（見 `ElderApp.tsx` 的註解與 `strings.common.
    // comingSoon`）。原始斷言在目前程式碼下必定逾時失敗，故改為斷言這個
    // 任務範圍內真正做得到、也真正該驗證的行為：綁定成功後**離開了配對畫面**
    // （不再看得到「綁定碼」欄位），並顯示佔位文字而非停在原地或報錯。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 201,
        json: async () => envelope({ elder_id: "e1", name: "王阿嬤", token: "tok" }),
      }),
    );
    renderApp();
    await userEvent.type(screen.getByLabelText("綁定碼"), "AB12CD");
    await userEvent.click(screen.getByRole("button", { name: "開始使用" }));
    await screen.findByText("這裡還在準備，請再等一下。");
    expect(screen.queryByLabelText("綁定碼")).not.toBeInTheDocument();
  });

  it.each([
    ["invite_not_found", "找不到這組號碼，請跟家人再確認一次。"],
    ["invite_used", "這組號碼已經用過了，請家人重新產生一組。"],
    ["invite_expired", "這組號碼過期了，請家人重新產生一組。"],
    ["too_many_attempts", "試太多次了，請家人重新產生一組。"],
  ])("綁定碼問題 %s 說的是長輩能照做的話", async (code, expected) => {
    // 「invite_expired」對長輩沒有意義。每一種失敗都要告訴他「下一步做什麼」。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ status: 400, json: async () => failure(code, "x") }),
    );
    renderApp();
    await userEvent.type(screen.getByLabelText("綁定碼"), "AB12CD");
    await userEvent.click(screen.getByRole("button", { name: "開始使用" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
  });

  it("綁定碼問題 invite_wrong_role 說的是「這組碼是給家人用的」而非查無此碼", async () => {
    // 家屬把自己的邀請碼給長輩掃／打時，後端回 409 invite_wrong_role——這與
    // 「查無此碼」「已過期」是完全不同的原因，混在一起講，長輩會拿著同一組本來
    // 就不是給他用的碼反覆重試。brief 原本沒有這個案例，是本輪要補的缺口。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ status: 409, json: async () => failure("invite_wrong_role", "x") }),
    );
    renderApp();
    await userEvent.type(screen.getByLabelText("綁定碼"), "AB12CD");
    await userEvent.click(screen.getByRole("button", { name: "開始使用" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "這組號碼是給家人用的，請家人給您長輩專用的那組。",
    );
  });

  it("家屬端送過來的碼會直接填好", () => {
    render(
      <ElderSession.Provider>
        <ElderApp prefilledCode="XY99ZZ" />
      </ElderSession.Provider>,
    );
    expect(screen.getByLabelText("綁定碼")).toHaveValue("XY99ZZ");
    expect(screen.getByText("已從家屬手機收到號碼")).toBeInTheDocument();
  });

  it("可以切到帳密登入再切回來", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "用過金孫？帳號密碼登入" }));
    expect(screen.getByLabelText("手機號碼")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "返回" }));
    expect(screen.getByLabelText("綁定碼")).toBeInTheDocument();
  });

  it("還沒配對過就用帳密登入時，說清楚要先掃碼", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ status: 403, json: async () => failure("not_paired", "x") }),
    );
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "用過金孫？帳號密碼登入" }));
    await userEvent.type(screen.getByLabelText("手機號碼"), "0912345678");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "這支手機還沒跟家人配對過，請先請家人給您綁定圖（QR）掃描一次。",
    );
  });
});

describe("QR 掃碼的六種錯誤", () => {
  // `talk/qrScanner.ts::QrScannerError` 有六種，不是兩種——brief 原始版本的
  // `SCANNER_ERRORS` 只給了 `denied`／`unsupported` 兩個鍵，型別是
  // `Record<QrScannerError, string>`：**這連 tsc 都過不了**（缺四個必要鍵），
  // 是「根本編譯不過」的缺陷。每一種都要有一句長輩看得懂、講得出下一步的話。
  const CASES: Array<[string, string]> = [
    ["denied", "需要相機權限才能掃描，也可以直接輸入號碼。"],
    ["not-found", "這台裝置沒有相機，請直接輸入號碼。"],
    ["in-use", "相機正被別的畫面用著，請直接輸入號碼，或關掉其他用相機的畫面再試一次。"],
    [
      "insecure-origin",
      "這個網址不能用相機，請改用家人給您、開頭是 https 的網址，或直接輸入號碼。",
    ],
    ["no-signal", "相機看不到畫面，請確認鏡頭沒被遮住，或直接輸入號碼。"],
    ["unsupported", "這個瀏覽器不能用相機，請直接輸入號碼。"],
  ];

  it.each(CASES)("%s 顯示長輩看得懂、知道下一步的話，並關閉相機", async (reason, expected) => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    act(() => {
      scannerState.onError?.(reason);
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    // 出錯就退回手動輸入畫面，相機要立刻關掉，不能留著指示燈亮著。
    expect(scannerState.stop).toHaveBeenCalled();
  });
});

describe("QR 掃碼的相機資源釋放", () => {
  it("按下改用輸入號碼會關閉相機、回到手動輸入", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    await userEvent.click(screen.getByRole("button", { name: "改用輸入號碼" }));
    expect(scannerState.stop).toHaveBeenCalled();
    expect(screen.getByLabelText("綁定碼")).toBeInTheDocument();
  });

  it("掃到碼後會關閉相機並送出綁定（method／路徑／body 皆正確）", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 201,
      json: async () => envelope({ elder_id: "e1", name: "陳阿公", token: "tok2" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    act(() => {
      scannerState.onCode?.("QR9987");
    });
    // 掃到就收工：相機立刻關閉，不必等送出結果回來才關。
    expect(scannerState.stop).toHaveBeenCalled();
    await screen.findByText("這裡還在準備，請再等一下。");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/device-bindings",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ code: "QR9987" }) }),
    );
  });

  it("離開這個畫面時（元件卸載）會關閉相機", async () => {
    const { unmount } = renderApp();
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    unmount();
    expect(scannerState.stop).toHaveBeenCalled();
  });
});
