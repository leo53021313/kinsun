/** 雙欄舞台：兩欄都在、窄螢幕以頁籤切換。 */

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StagePage } from "./StagePage";

/**
 * 可控制的假 `matchMedia`。
 *
 * ⚠️ jsdom 沒有這個 API（實測 `typeof window.matchMedia` 是 `undefined`），所以
 * **沒有呼叫這支的測試都跑在「不是寬螢幕」的路徑上**——那正是頁籤模式的語意，
 * 既有測試因此完全不受影響。
 */
function stubMatchMedia(isWide: boolean) {
  const listeners = new Set<() => void>();
  const query = {
    matches: isWide,
    addEventListener: (_event: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_event: string, listener: () => void) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return {
    /** 模擬使用者把視窗拉寬／縮窄，或按 Ctrl+ 改變字級（`lg` 是 CSS px）。 */
    setWide(next: boolean) {
      query.matches = next;
      act(() => listeners.forEach((listener) => listener()));
    },
  };
}

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
  // ⚠️ 歸零放在 beforeEach 而非 afterEach：`@testing-library/react` 的自動 cleanup
  // 也是 afterEach，而它**晚於**本檔的 afterEach 執行——上一條測試卸載時
  // `BindScreen` 的 effect cleanup 會再呼叫一次 `scanner.stop()`，那一筆就會落在
  // 下一條測試的帳上（實測：寬螢幕那條因此看到一次不存在的 stop）。
  scannerState.stop.mockClear();
  scannerState.createCount = 0;
});
afterEach(() => {
  vi.unstubAllGlobals();
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

/**
 * ⚠️ **全分支審查抓到的 Important 2**：`elderVisible` 原本是 `pane === "elder"`，
 * 而頁籤是 `lg:hidden`。組員把視窗縮窄（或按 Ctrl+ 放大投影字級——Tailwind 的 `lg`
 * 是 1024 CSS px，縮放直接改變它）→ 點「家屬端」→ 再放大回去，兩欄又同時可見，但
 * `pane` 仍是 `"guardian"`。長輩欄看起來完全正常（`useTalk` 的 cleanup 把字幕重設回
 * 「按住下面的麥克風說話」、avatar 是 😊），麥克風卻永遠打不開，而 `lg` 以上頁籤是
 * `display:none`——畫面上不存在任何能把 `pane` 撥回來的 UI。而投影機上的那一欄，
 * 正是所有人在看的那一欄。
 *
 * 這裡以相機當觀察窗（`visible` 那條鏈上唯一在無頭環境測得到的效果，麥克風與長連線
 * 走的是同一個 prop）。
 */
describe("寬螢幕兩欄同時可見時的長輩欄", () => {
  it("點頁籤不可以把還開著的長輩欄關掉（兩欄都看得見，沒有「切走」這回事）", async () => {
    stubMatchMedia(true);
    render(<StagePage />);
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    expect(scannerState.createCount).toBe(1);

    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));

    expect(scannerState.stop).not.toHaveBeenCalled();
    expect(scannerState.createCount).toBe(1);
  });

  it("窄螢幕切到家屬端之後把螢幕變寬，長輩欄要活過來", async () => {
    const media = stubMatchMedia(false);
    render(<StagePage />);
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    // 窄螢幕的既有行為不變：切走就關掉相機。
    expect(scannerState.stop).toHaveBeenCalled();
    expect(scannerState.createCount).toBe(1);

    media.setWide(true);

    // 兩欄又同時看得見了：長輩欄必須跟著回來，否則它會停在一個看起來正常、
    // 實際上麥克風永遠打不開的狀態，而且沒有任何 UI 救得回來。
    expect(scannerState.createCount).toBe(2);
  });
});
