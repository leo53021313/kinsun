/**
 * 人稱與角色名的守門測試。
 *
 * 2026-08-07 的新視覺把角色從阿金改名為阿白、自述改第一人稱，但那份交接只指名
 * `RAG/app/`，`web/` 整份文案停在改版前。網頁版是發表要用的 demo 載體，兩端說法
 * 不一致，觀眾看到的就是兩個產品。
 *
 * ⚠️ **這裡不能用「全庫不准出現金孫」一條斷言了事**，那正是交接文件反覆警告的
 * 錯誤做法：「金孫」有兩種身分，只有其中一種要改。
 *
 * - **角色＝阿白**：長輩對話的那隻北極熊。自述一律第一人稱「我」；系統描述它時
 *   （狀態文字、aria-label）用第三人稱「阿白」；家屬端一律第三人稱。
 * - **服務＝金孫**：品牌字樣、App 名稱、同意條款主體、「連不上金孫」這種指服務
 *   本身的句子。**不要改。**
 *
 * 所以下面分兩組列舉：該是阿白的地方不准有金孫，該是金孫的地方必須還在。
 */

import { describe, expect, it } from "vitest";

import { strings } from "./strings";

describe("角色文案：該叫阿白的地方不准殘留服務名", () => {
  it.each([
    ["talk.fallback", strings.talk.fallback],
    ["talk.micPermission", strings.talk.micPermission],
    ["talk.listening", strings.talk.listening],
    ["talk.listeningTapHint", strings.talk.listeningTapHint],
    ["talk.thinking", strings.talk.thinking],
    ["talk.noAnswer", strings.talk.noAnswer],
    ["talk.queued", strings.talk.queued(2)],
    ["talk.status.speaking", strings.talk.status.speaking],
    ["talk.statusSub.idle", strings.talk.statusSub.idle],
    ["talk.statusSub.error", strings.talk.statusSub.error],
    ["talk.actions.waitWhileSpeaking", strings.talk.actions.waitWhileSpeaking],
    ["talk.collapsedPrefix", strings.talk.collapsedPrefix],
    ["talk.companionTitle", strings.talk.companionTitle],
    ["elderNotifications.title", strings.elderNotifications.title],
    ["elderNotifications.empty", strings.elderNotifications.empty],
    ["elderNotifications.bell", strings.elderNotifications.bell],
    ["notifications.empty", strings.notifications.empty],
    ["elderDetail.noSummaries", strings.elderDetail.noSummaries],
  ])("%s 不含「金孫」", (_key, text) => {
    expect(text).not.toContain("金孫");
  });

  it.each([
    ["talk.fallback", strings.talk.fallback],
    ["talk.listening", strings.talk.listening],
    ["talk.thinking", strings.talk.thinking],
    ["talk.noAnswer", strings.talk.noAnswer],
  ])("%s 是阿白自述，用第一人稱「我」開頭", (_key, text) => {
    expect(text.startsWith("我")).toBe(true);
  });

  it("狀態帶是系統在描述角色，用第三人稱；副標是阿白自述，用第一人稱", () => {
    // 兩層人稱在同一個畫面上並存：狀態帶「阿白正在說話」是系統在講它，
    // 副標「我在這裡等您」是它自己在講。這是交付文件〈第一人稱的三條界線〉
    // 的第二條，最容易在改文案時被抹平成同一種。
    expect(strings.talk.status.speaking).toBe("阿白正在說話");
    expect(strings.talk.statusSub.idle.startsWith("我")).toBe(true);
    expect(strings.talk.statusSub.error.startsWith("我")).toBe(true);
  });

  it("長輩端的提醒頁叫「阿白的提醒」，不出現「通知」二字", () => {
    // 接手指示規則 5：長輩端絕不出現「通知」，家屬端才用。
    expect(strings.elderNotifications.title).toBe("阿白的提醒");
    expect(strings.elderNotifications.title).not.toContain("通知");
    expect(strings.elderNotifications.empty).not.toContain("通知");
  });
});

describe("服務名：這些地方的「金孫」必須留著", () => {
  it("品牌字樣不改", () => {
    expect(strings.gate.brand).toBe("金孫");
  });

  it("同意條款的主體是服務，不是角色", () => {
    expect(strings.guardianHome.consent).toContain("金孫");
  });

  it("「連不上金孫」指的是連不上服務", () => {
    expect(strings.elderBind.bindFailed).toContain("金孫");
  });

  it("「用過金孫？」問的是用過這個服務", () => {
    expect(strings.elderBind.loginLink).toContain("金孫");
  });

  it("服務狀態頁的分項說明講的是服務能力，不是角色", () => {
    // gate 是進入前的服務大廳（`gate.brand` 就是品牌字樣），這裡描述的是 ASR／TTS
    // 兩個服務元件的健康狀態，性質同「金孫會在早上七點產生摘要」——講服務。
    expect(strings.gate.degradedNote.tts).toContain("金孫");
    expect(strings.gate.degradedNote.asr).toContain("金孫");
  });
});
