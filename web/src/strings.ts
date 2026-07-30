/**
 * zh-TW 字串常數集中（沿用 ✅ D-50：不導入 i18n 框架，單語系）。
 *
 * 為什麼後端不直接回中文狀態文字：後端回的是機器可讀的狀態碼，文案歸前端。
 * 這樣改一句話不必動後端、不必重啟服務——展示前一天要改文案是常態。
 */

export const strings = {
  common: {
    loading: "載入中…",
    retry: "再試一次",
    close: "關閉",
  },
  gate: {
    brand: "金孫",
    slogan: "陪伴長輩的家庭夥伴",
    checking: "正在確認服務狀態…",
    start: "開始使用",
    overall: {
      available: "服務正常運作中",
      degraded: "服務可以使用，但有部分功能受限",
      starting: "服務正在啟動，請稍候…",
      down: "服務目前無法使用",
    } as Record<string, string>,
    /** 分項名稱。鍵與後端 components 的鍵一一對應。 */
    component: {
      database: "資料庫",
      asr: "聽懂您說話",
      tts: "開口說話",
      llm: "對話思考",
      scheduler: "準時提醒",
    } as Record<string, string>,
    componentStatus: {
      ok: "正常",
      loading: "啟動中",
      down: "無法使用",
      unknown: "狀態不明",
    } as Record<string, string>,
    /** 部分受限時，逐項告訴使用者少了什麼——「部分受限」四個字沒有資訊量。 */
    degradedNote: {
      tts: "金孫聽得懂您說話，但暫時不會出聲，回答只會顯示文字。",
      llm: "對話回應可能不穩定。",
      scheduler: "設定的提醒暫時不會準時響。",
      database: "資料暫時無法讀寫。",
      asr: "金孫暫時聽不懂您說話。",
    } as Record<string, string>,
    statusUnreachable: "連不上服務，可能是伺服器沒有啟動。",
  },
  stage: {
    elderTab: "長輩端",
    guardianTab: "家屬端",
    elderTitle: "長輩的手機",
    guardianTitle: "家屬的手機",
  },
};
