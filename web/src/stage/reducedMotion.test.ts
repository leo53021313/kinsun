/**
 * `prefersReducedMotion`：`stage/BloomTransition.tsx` 與 `notify/NotificationBanner.tsx`
 * 共用同一份判斷式，見該檔說明。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { prefersReducedMotion } from "./reducedMotion";

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

describe("prefersReducedMotion", () => {
  it("使用者開了減少動態效果時回 true", () => {
    mockReducedMotion(true);
    expect(prefersReducedMotion()).toBe(true);
  });

  it("使用者沒有開時回 false", () => {
    mockReducedMotion(false);
    expect(prefersReducedMotion()).toBe(false);
  });
});
