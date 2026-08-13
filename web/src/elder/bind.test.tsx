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

  it("輸入綁定碼成功後進到對講機", async () => {
    // ⚠️ Task 7 當時對講機還沒接上（`ElderApp` 的 talk 路由是佔位文字），這條
    // 測試因此暫時改成斷言「離開了配對畫面」。P3 Task 8 接上 `TalkScreen` 之後
    // 恢復成 brief 原本要驗的事：綁定成功後**真的到得了對講機**，麥克風鍵就在
    // 眼前——這才是長輩走完配對之後唯一在意的結果。
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
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
    expect(screen.queryByLabelText("綁定碼")).not.toBeInTheDocument();
  });

  it("手動輸入綁定碼會把完整輸入送出，不會被截斷（method／路徑／body 皆正確）", async () => {
    // ⚠️ 審查發現：長輩多半用手打（見本檔開頭註解），但先前只有掃碼那條路徑
    // 斷言了送出的 method／路徑／body。審查實測過一個變異：
    // `submit(code)` 改成 `submit(code.slice(0, 3))`——長輩打完整六碼、
    // 實際只送前三碼，後端必回查無此碼，他對著正確的碼反覆重打——原本的
    // 測試組合毫無察覺（19/19 仍全綠）。這裡補上手打路徑同等級的線路契約
    // 斷言。
    const fetchMock = vi.fn().mockResolvedValue({
      status: 201,
      json: async () => envelope({ elder_id: "e1", name: "王阿嬤", token: "tok" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await userEvent.type(screen.getByLabelText("綁定碼"), "AB12CD");
    await userEvent.click(screen.getByRole("button", { name: "開始使用" }));
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/device-bindings",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ code: "AB12CD" }) }),
    );
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

  // ⚠️ 這條守的是「跨欄連動」實際會發生的形狀：長輩欄在家屬按下「送到長輩的
  // 手機」之前多半早就掛著（雙欄舞台一開場兩欄就都在），`prefilledCode` 是家屬
  // 按下去那一刻才從 `undefined` 變成有值的——不是「掛載當下就已經有值」。
  // ⚠️ 全分支審查修正：`prefilledCode` 是**事件**（帶遞增 `seq` 的
  // `{ code, seq }`）不是單純的值——同一個碼被重複送出時，字串本身不會變，
  // 若只比較字串會判斷成「沒有變化」而略過同步（見下面「同一組碼再送一次」
  // 那條測試）。
  it("家屬端送過來的碼會直接填好", () => {
    const { rerender } = render(
      <ElderSession.Provider>
        <ElderApp />
      </ElderSession.Provider>,
    );
    expect(screen.getByLabelText("綁定碼")).toHaveValue("");
    expect(screen.queryByText("已從家屬手機收到號碼")).not.toBeInTheDocument();
    rerender(
      <ElderSession.Provider>
        <ElderApp prefilledCode={{ code: "AB12CD", seq: 1 }} />
      </ElderSession.Provider>,
    );
    expect(screen.getByLabelText("綁定碼")).toHaveValue("AB12CD");
    expect(screen.getByText("已從家屬手機收到號碼")).toBeInTheDocument();
  });

  // ⚠️ 全分支審查發現的 Important 1、失效情境 1：長輩用這組碼配對成功、進了
  // 對講機，後來被登出（家屬重新產生綁定碼，或他自己登出）——`ElderApp` 的
  // 路由把 `BindScreen` 換掉又換回來，是全新的一次掛載，不是同一個元件實例的
  // rerender。此時 `StagePage` 那份 `prefilledCode` 狀態沒有人清掉，仍是舊值；
  // 若把「掛載當下 props 裡已經存在的碼」直接當成剛剛發生的事件，長輩會在毫無
  // 預兆的情況下看到一個已經用掉的舊碼、以及「已從家屬手機收到號碼」的假綠字。
  it("已經送過的舊碼在全新一次掛載時不會被當成剛剛才發生的事（審查情境 1：配對成功又被登出）", () => {
    const delivery = { code: "AB12CD", seq: 1 };
    const first = render(
      <ElderSession.Provider>
        <ElderApp prefilledCode={delivery} />
      </ElderSession.Provider>,
    );
    first.unmount();
    render(
      <ElderSession.Provider>
        <ElderApp prefilledCode={delivery} />
      </ElderSession.Provider>,
    );
    expect(screen.getByLabelText("綁定碼")).toHaveValue("");
    expect(screen.queryByText("已從家屬手機收到號碼")).not.toBeInTheDocument();
  });

  // ⚠️ 全分支審查發現的 Important 1、失效情境 2：長輩自己把欄位改壞或清掉是
  // 現場常見的情形（他會先試著自己打），家屬發現後切回去再按一次同一顆「送到
  // 長輩的手機」——這一次送出的碼字串與上次相同，若只比較字串本身會被判斷成
  // 「沒有變化」而不同步，按鈕看起來像壞了。`seq` 遞增才能分辨「這是新的一次
  // 送出」。
  it("家屬對同一組碼再送一次（seq 遞增），就算碼相同也要能再次蓋掉長輩自己打的內容（審查情境 2）", async () => {
    // ⚠️ 從 `undefined` 開始、用 `rerender` 送出第一次——跟「掛載當下就已經有
    // 值」（不會在真實舞台發生的情境）不同，這裡模擬的是配對畫面本來就掛著、
    // 家屬才按下第一次送出。
    const { rerender } = render(
      <ElderSession.Provider>
        <ElderApp />
      </ElderSession.Provider>,
    );
    rerender(
      <ElderSession.Provider>
        <ElderApp prefilledCode={{ code: "AB12CD", seq: 1 }} />
      </ElderSession.Provider>,
    );
    expect(screen.getByLabelText("綁定碼")).toHaveValue("AB12CD");
    await userEvent.clear(screen.getByLabelText("綁定碼"));
    await userEvent.type(screen.getByLabelText("綁定碼"), "打壞了");
    rerender(
      <ElderSession.Provider>
        <ElderApp prefilledCode={{ code: "AB12CD", seq: 2 }} />
      </ElderSession.Provider>,
    );
    expect(screen.getByLabelText("綁定碼")).toHaveValue("AB12CD");
  });

  it("可以切到帳密登入再切回來", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "用過金孫？帳號密碼登入" }));
    expect(screen.getByLabelText("手機號碼")).toBeInTheDocument();
    // ⚠️ 返回鍵說的是「回去輸入號碼」而不是「返回」——從這裡按返回是回到配對畫面，
    // 不是回到對講機，兩個畫面的返回鍵各講各的下一步。
    await userEvent.click(screen.getByRole("button", { name: "回去輸入號碼" }));
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
      "這支手機還沒跟家人配對過，請先請家人給您方塊圖掃描一次。",
    );
  });

  it("帳密登入的 401 是密碼打錯，不可以把長輩踢回配對畫面", async () => {
    // ⚠️ 全分支審查修 Critical 1 時，長輩端的對講機與提醒列表都接上了「401 就清掉
    // 登入、導回配對」。**登入畫面是唯一不可以這樣做的地方**：這裡的 401 是「號碼
    // 或密碼不對」，要顯示給人看、讓他重打，把他踢回配對畫面等於每打錯一次密碼就
    // 被趕出去一次（`session/useSignOutOnAuthError.ts` 開頭也寫著同一句警告）。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ status: 401, json: async () => failure("invalid_credentials", "x") }),
    );
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "用過金孫？帳號密碼登入" }));
    await userEvent.type(screen.getByLabelText("手機號碼"), "0912345678");
    await userEvent.type(screen.getByLabelText("密碼"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "號碼或密碼不對，可以請家人幫忙確認。",
    );
    // 還在登入畫面（號碼與密碼都還在），不是被送回配對畫面重打一次綁定碼。
    expect(screen.getByLabelText("手機號碼")).toHaveValue("0912345678");
  });

  it("手機號碼欄位格式不對時，照實顯示後端訊息而非「連線失敗」", async () => {
    // ⚠️ 審查發現：手機號碼欄空白或只打了「09」會讓後端
    // ElderLoginIn.phone: Field(min_length=8) 觸發 422 validation_error，
    // 回「輸入資料格式不正確」——這句話已是繁中人話（D-24）。原始版本把
    // 所有非 401／403 一律顯示「連線失敗」，長輩會去確認 Wi-Fi、反覆重試，
    // 永遠不會想到是欄位沒填好；guardian/LoginScreen.tsx 已修過同一類問題，
    // 此處補齊同一套原則。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 422,
        json: async () => failure("validation_error", "輸入資料格式不正確"),
      }),
    );
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "用過金孫？帳號密碼登入" }));
    await userEvent.type(screen.getByLabelText("手機號碼"), "09");
    await userEvent.type(screen.getByLabelText("密碼"), "x");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("輸入資料格式不正確");
  });

  it("帳密登入把手機號碼與密碼各自正確送出，不會對調（method／路徑／body 皆正確）", async () => {
    // ⚠️ 審查發現：審查實測過一個變異——`loginElder(phone, password)` 改成
    // `loginElder(password, phone)`，手機號碼與密碼對調送出，長輩永遠登不
    // 進去——原本的測試組合毫無察覺。這裡補上線路契約斷言。
    const fetchMock = vi.fn().mockResolvedValue({
      status: 201,
      json: async () => envelope({ elder_id: "e1", name: "王阿嬤", token: "tok" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "用過金孫？帳號密碼登入" }));
    await userEvent.type(screen.getByLabelText("手機號碼"), "0912345678");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/elder-sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ phone: "0912345678", password: "correct-horse-8" }),
      }),
    );
  });
});

describe("忙碌狀態防連按", () => {
  /** 手動控制的 promise：`mockResolvedValue` 在同一個 microtask 就解出，看不見
   *  「送出中」這個中間狀態——這份計畫栽過三次的教訓，見 brief 的既有提醒。 */
  function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((res) => {
      resolve = res;
    });
    return { promise, resolve };
  }

  it("綁定送出期間按鈕忙碌中，連點兩下只送出一次請求", async () => {
    const { promise, resolve } = deferred<{ status: number; json: () => Promise<unknown> }>();
    const fetchMock = vi.fn().mockReturnValue(promise);
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await userEvent.type(screen.getByLabelText("綁定碼"), "AB12CD");
    const button = screen.getByRole("button", { name: "開始使用" });
    await userEvent.click(button);
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolve({
      status: 201,
      json: async () => envelope({ elder_id: "e1", name: "王阿嬤", token: "tok" }),
    });
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
  });

  it("登入送出期間按鈕忙碌中，連點兩下只送出一次請求", async () => {
    const { promise, resolve } = deferred<{ status: number; json: () => Promise<unknown> }>();
    const fetchMock = vi.fn().mockReturnValue(promise);
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "用過金孫？帳號密碼登入" }));
    await userEvent.type(screen.getByLabelText("手機號碼"), "0912345678");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    const button = screen.getByRole("button", { name: "登入" });
    await userEvent.click(button);
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolve({
      status: 201,
      json: async () => envelope({ elder_id: "e1", name: "王阿嬤", token: "tok" }),
    });
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
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
    ["in-use", "別的畫面正在用相機，請直接輸入號碼，或關掉那個畫面再試一次。"],
    [
      "insecure-origin",
      "這個網址不能用相機，請改用家人給您、開頭是 https 的網址，或直接輸入號碼。",
    ],
    ["no-signal", "相機看不到畫面，請確認鏡頭沒被遮住，或直接輸入號碼。"],
    ["unsupported", "這個瀏覽器不能用相機，請直接輸入號碼。"],
  ];

  it.each(CASES)("%s 顯示長輩看得懂、知道下一步的話，並關閉相機", async (reason, expected) => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "掃描方塊圖" }));
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
    await userEvent.click(screen.getByRole("button", { name: "掃描方塊圖" }));
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
    await userEvent.click(screen.getByRole("button", { name: "掃描方塊圖" }));
    act(() => {
      scannerState.onCode?.("QR9987");
    });
    // 掃到就收工：相機立刻關閉，不必等送出結果回來才關。
    expect(scannerState.stop).toHaveBeenCalled();
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/device-bindings",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ code: "QR9987" }) }),
    );
  });

  it("離開這個畫面時（元件卸載）會關閉相機", async () => {
    const { unmount } = renderApp();
    await userEvent.click(screen.getByRole("button", { name: "掃描方塊圖" }));
    unmount();
    expect(scannerState.stop).toHaveBeenCalled();
  });
});
