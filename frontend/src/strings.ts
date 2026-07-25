/** LIFF 端 UI 文案集中（✅ 庚-31／D-50）：改文案只動此檔。 */

export const strings = {
  common: {
    loading: "載入中…",
    loadFailed: "載入失敗，請稍後再試",
    saveFailed: "儲存失敗，請稍後再試",
    deleteFailed: "刪除失敗，請稍後再試",
    backToElders: "← 返回長輩清單",
    edit: "編輯",
    delete: "刪除",
    add: "新增",
    update: "更新",
    cancelEdit: "取消編輯",
  },
  app: {
    initFailed: "初始化失敗，請稍後再試",
  },
  elders: {
    title: "您管理的長輩",
    nameRequired: "請輸入長輩稱呼",
    createFailed: "建立失敗，請稍後再試",
    inviteFailed: "產生邀請碼失敗，請稍後再試",
    elderCodeNotice: "長輩綁定碼（請交給長輩在 LINE 貼上，24 小時內有效）：",
    guardianCodeNotice: "家屬邀請碼（請交給其他家屬在 LINE 貼上，24 小時內有效）：",
    linkSchedules: "行程",
    linkHealthReport: "健康報告",
    inviteGuardian: "邀請家屬",
    addHeading: "新增長輩",
    namePlaceholder: "長輩稱呼（例：阿公、王媽媽）",
    createButton: "建立",
  },
  schedules: {
    title: "行程管理",
    empty: "還沒有任何提醒，從下方新增第一筆。",
    titleRequired: "請填寫提醒內容",
    whenRequired: "請填寫提醒時間，格式請照欄位裡的範例",
    editHint: "修改後請重新填一次提醒時間",
    editHeading: "編輯提醒",
    addHeading: "新增提醒",
    kindLabel: "提醒類型",
    titleLabel: "提醒內容",
    titlePlaceholder: (kind: string) =>
      kind === "medication"
        ? "例：降血壓藥"
        : kind === "appointment"
          ? "例：心臟科回診 林口長庚"
          : "例：去公園散步",
    slotsLabel: "提醒時段（可複選）",
    customTimeLabel: "或直接指定時刻（選填，會蓋過上面的時段）",
    whenLabel: (kind: string) => (kind === "appointment" ? "回診日期" : "提醒時間"),
    whenPlaceholder: (kind: string) =>
      kind === "appointment" ? "2026-07-30 10:30（時間可省略）" : "每天 17:00／每週三 15:00",
    byElder: "（長輩自己交代的）",
  },
  healthReport: {
    title: "健康報告（近 30 天）",
    riskEventsHeading: "危急事件",
    noRiskEvents: "近 30 天無危急事件",
    remindersHeading: "提醒紀錄",
    noReminders: "近 30 天無提醒紀錄",
  },
} as const;
