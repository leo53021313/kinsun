/** 雙欄舞台：兩欄都在、窄螢幕以頁籤切換。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StagePage } from "./StagePage";

/**
 * 同 `elder/bind.test.tsx` 的既有慣例：整支 `talk/qrScanner.ts` 換成假的，
 * 只留呼叫端傳入的 `onCode`／`onError` 存起來，測試自己決定何時觸發。這裡
 * 要驗證的是**切頁籤**這個 `StagePage` 層級的行為，所以在這個檔案獨立重建
 * 一份同款 mock（各測試檔自己顧自己的 mock，同本專案既有慣例），不是在
 * `elder/bind.test.tsx` 裡驗證得到的。
 */
const scannerState = vi.hoisted(() => ({ stop: vi.fn(), createCount: 0 }));
vi.mock("@/talk/qrScanner", () => ({
  createQrScanner: () => {
    scannerState.createCount += 1;
    return { stop: scannerState.stop };
  },
}));

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  scannerState.stop.mockClear();
  scannerState.createCount = 0;
});

describe("StagePage", () => {
  it("兩支手機同時在畫面上", () => {
    render(<StagePage />);
    expect(screen.getByRole("region", { name: "長輩的手機" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "家屬的手機" })).toBeInTheDocument();
  });

  it("長輩欄顯示真正的配對畫面，不是佔位元件（P3 Task 7 接上 ElderApp）", () => {
    render(<StagePage />);
    expect(screen.getByText("掃描家人給的方塊圖，或輸入號碼")).toBeInTheDocument();
  });

  it("窄螢幕的切換頁籤兩個都在", () => {
    render(<StagePage />);
    expect(screen.getByRole("tab", { name: "長輩端" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "家屬端" })).toBeInTheDocument();
  });

  it("預設選中長輩端", () => {
    render(<StagePage />);
    expect(screen.getByRole("tab", { name: "長輩端" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "家屬端" })).toHaveAttribute("aria-selected", "false");
  });

  it("點頁籤可以切換", async () => {
    render(<StagePage />);
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    expect(screen.getByRole("tab", { name: "家屬端" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "長輩端" })).toHaveAttribute("aria-selected", "false");
  });

  it("長輩欄正在掃 QR 時切到家屬端頁籤會關閉相機（審查發現的 Critical）", async () => {
    // ⚠️ 窄螢幕是頁籤擇一顯示，非活動欄只是被 CSS `hidden` 蓋住、元件仍掛著
    // ——`MediaStream` 軌道與 `display:none` 無關，不會因為看不見就自己關閉。
    // 若切頁籤不會讓長輩欄停止掃描，相機會一直開到分頁關閉為止。
    render(<StagePage />);
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    expect(scannerState.createCount).toBe(1);
    expect(scannerState.stop).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    expect(scannerState.stop).toHaveBeenCalled();
    // ⚠️ 只斷言 stop() 被呼叫還不夠——一個更隱蔽的半套修法是「切走時關掉舊的，
    // 但沒同時擋住『再建一顆新的』」，那樣 stop() 一樣會被呼叫到，相機卻立刻
    // 重新開啟，指示燈依然亮著。切走後 createCount 必須維持 1（沒有再建立
    // 任何新的 scanner），camera 才是真的關閉而非「關了又馬上開」。
    expect(scannerState.createCount).toBe(1);
  });

  it("切回長輩端頁籤時，掃描仍在進行中會自動恢復（不強迫重新按「掃描 QR 碼」）", async () => {
    render(<StagePage />);
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    scannerState.stop.mockClear();
    await userEvent.click(screen.getByRole("tab", { name: "長輩端" }));
    // 切回來後畫面仍是「把方塊圖對準框框」的掃描畫面，不是被強迫退回手動輸入。
    expect(screen.getByText("把家人給的方塊圖對準框框")).toBeInTheDocument();
    // 切回來要重新要求鏡頭（權限已授予，瀏覽器不會再跳一次對話框）才能真的
    // 恢復畫面，不是留著一個早就被關掉的舊串流。
    expect(scannerState.createCount).toBe(2);
  });
});
