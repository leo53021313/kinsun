/**
 * 模擬系統通知橫幅（W-13）。
 *
 * ⚠️ 這是**畫面上的模擬**，不是瀏覽器的 Notification API。後端只支援 Expo 推播
 * （platform 白名單只有 android／ios），網頁沒有那條路；而展示要的正是「手機上
 * 跳出通知」的那個畫面感。
 *
 * ⚠️ 審查修正（2026-07-31）：live region 的 `role="status"` 已移到
 * `stage/PhoneFrame.tsx` 那個永遠掛載的通知容身處（見 `PhoneFrame.test.tsx`）。
 * 本元件單獨測試時不再有 `role="status"` 可以查，選取卡片一律改用
 * `data-testid="notification-banner"`。
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { detectOs } from "./osStyle";
import { NotificationBanner } from "./NotificationBanner";

const ITEM = { id: "n1", title: "金孫", content: "提醒您：降血壓藥", at: 1754000000 };

function banner() {
  return screen.getByTestId("notification-banner");
}

/** 同 stage/TearTransition.test.tsx 既有的假 matchMedia 作法。 */
function mockReducedMotion(reduced: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: reduced && query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NotificationBanner", () => {
  it("沒有東西時不畫任何東西", () => {
    const { container } = render(
      <NotificationBanner item={null} os="ios" onDismiss={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("顯示標題與內容", () => {
    render(<NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />);
    expect(screen.getByText("金孫")).toBeInTheDocument();
    expect(screen.getByText("提醒您：降血壓藥")).toBeInTheDocument();
  });

  it('本身不宣告 role="status"——live region 由 PhoneFrame 的通知容身處提供', () => {
    // ⚠️ 這裡曾經是本元件自己宣告 role="status" 的地方：容器與內容因 key 而
    // 同一次 DOM 變更一起冒出來，AT 收到的是「新元素出現」而非「區域文字變
    // 了」，多數 AT 因此不會播報（審查修正）。這條測試釘住「不要加回來」。
    render(<NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("可以手動關掉", async () => {
    const onDismiss = vi.fn();
    render(<NotificationBanner item={ITEM} os="ios" onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: "關閉" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("卡片本體不吃點擊事件，只有關閉鍵吃得到——橫幅底下的按鈕仍按得到", () => {
    // ⚠️ 審查發現的 Minor：橫幅從 PhoneFrame 的 y=40px 起、高約 62px，恰好整條
    // 蓋住長輩欄的鈴鐺列（56px）與登出鍵。卡片本體必須維持 pointer-events-none，
    // 只讓關閉鍵自己 pointer-events-auto，點擊才穿得過去給底下真正的按鈕。
    render(<NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />);
    expect(banner().className).toContain("pointer-events-none");
    expect(screen.getByRole("button", { name: "關閉" }).className).toContain(
      "pointer-events-auto",
    );
  });

  it("兩種作業系統的樣式不同", () => {
    const { rerender } = render(
      <NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />,
    );
    const iosClass = banner().className;
    rerender(<NotificationBanner item={ITEM} os="android" onDismiss={vi.fn()} />);
    expect(banner().className).not.toBe(iosClass);
  });

  it("換一則時重新播進場動畫", () => {
    // 沒有 key 的話 React 會沿用同一個 DOM 節點，第二則會靜靜地換掉字、
    // 完全沒有「又來一則」的感覺——而那正是展示要的效果。
    const { rerender } = render(
      <NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />,
    );
    const first = banner();
    rerender(
      <NotificationBanner
        item={{ ...ITEM, id: "n2", content: "王阿嬤剛剛說：「我頭有點暈」" }}
        os="ios"
        onDismiss={vi.fn()}
      />,
    );
    expect(banner()).not.toBe(first);
  });

  it("連續來好幾則時，畫面上只會看到最後一則、不會疊加或殘留前面的內容", () => {
    // brief 沒有排隊機制：呼叫端傳新的 item 進來，舊的那則直接被取代。這裡把
    // 三則排在一起驗證「不管來幾則，畫面上永遠只有一張卡片、內容也永遠是
    // 最新那則」——不是排隊，也不是疊圖。
    const second = { ...ITEM, id: "n2", content: "王阿嬤剛剛說：「我頭有點暈」" };
    const third = { ...ITEM, id: "n3", content: "該量血壓囉" };
    const { rerender } = render(
      <NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />,
    );
    rerender(<NotificationBanner item={second} os="ios" onDismiss={vi.fn()} />);
    rerender(<NotificationBanner item={third} os="ios" onDismiss={vi.fn()} />);

    expect(screen.queryByText(ITEM.content)).not.toBeInTheDocument();
    expect(screen.queryByText(second.content)).not.toBeInTheDocument();
    expect(screen.getByText(third.content)).toBeInTheDocument();
    expect(screen.getAllByTestId("notification-banner")).toHaveLength(1);
  });

  it("使用者關了動態效果時，進場不套用滑入動畫的類名", () => {
    mockReducedMotion(true);
    render(<NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />);
    expect(banner().className).not.toContain("animate-");
  });

  it("預設（沒有關動態效果）時套用滑入動畫的類名", () => {
    mockReducedMotion(false);
    render(<NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />);
    expect(banner().className).toContain("animate-");
  });

  it('size="big" 時字級放大到長輩端下限，預設 size="normal" 維持原字級', () => {
    // ⚠️ 審查發現的 Important：brief 原始版本標題／內容固定 12px／14px，這張
    // 橫幅一旦被塞進長輩欄，恰好是長輩該讀的那句話卻小到看不清（同一個坑
    // TalkScreen.tsx 的未讀紅點已經開過一次）。
    const { rerender } = render(
      <NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />,
    );
    expect(screen.getByText(ITEM.title).className).toContain("text-xs");
    expect(screen.getByText(ITEM.content).className).toContain("text-sm");

    rerender(
      <NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} size="big" />,
    );
    expect(screen.getByText(ITEM.title).className).toContain("text-elder-min");
    expect(screen.getByText(ITEM.content).className).toContain("text-elder-min");
  });

  it('關閉鍵可點擊目標依 size 放大：normal 48px，big 56px', () => {
    // ⚠️ 審查發現的 Important：brief 原始版本沒有任何 min-h／size，實際高度
    // 只有約 18px、寬度約 28px——連 WCAG 2.5.5 的 44px 都差得遠。
    const { rerender } = render(
      <NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "關閉" }).className).toContain("size-12");

    rerender(
      <NotificationBanner item={ITEM} os="ios" onDismiss={vi.fn()} size="big" />,
    );
    expect(screen.getByRole("button", { name: "關閉" }).className).toContain("size-14");
  });
});

describe("detectOs", () => {
  it.each([
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)", "ios"],
    ["Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)", "ios"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "ios"],
    ["Mozilla/5.0 (Linux; Android 14; Pixel 8)", "android"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "android"],
  ])("%s → %s", (ua, expected) => {
    expect(detectOs(ua)).toBe(expected);
  });
});
