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
    loadFailed: "載入失敗，請稍後再試。",
    loadFailedShort: "載入失敗",
    connectionFailed: "連線失敗，請稍後再試。",
    saveFailed: "儲存失敗，請稍後再試。",
    deleteFailed: "刪除失敗，請稍後再試。",
    cancel: "取消",
    delete: "刪除",
    edit: "編輯",
    create: "新增",
    update: "更新",
    cancelEdit: "取消編輯",
    login: "登入",
    back: "返回",
    passwordLabel: "密碼",
    passwordPlaceholder: "至少 8 碼",
    emailLabel: "Email",
    emailPlaceholder: "you@example.com",
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
  guardianLogin: {
    title: "家屬登入",
    wrongCredentials: "帳號或密碼不對，請再試一次。",
    registerLink: "還沒有帳號？註冊",
  },
  guardianRegister: {
    title: "家屬註冊",
    passwordTooShort: "密碼至少 8 碼。",
    emailTaken: "這個 Email 已經註冊過了，請直接登入。",
    nameLabel: "您的稱呼",
    namePlaceholder: "例如：兒子小明",
    submit: "註冊並登入",
    loginLink: "已經有帳號？登入",
  },
  guardianHome: {
    title: "我的長輩",
    nameRequired: "請先輸入長輩的稱呼。",
    addFailed: "新增失敗",
    logout: "登出",
    notify: "通知",
    addElderSection: "新增長輩",
    elderNameLabel: "長輩稱呼",
    elderNamePlaceholder: "例如：阿公",
    consent:
      "建立後，金孫會記錄長輩與它的對話內容（文字與語音），用來陪伴關懷、產生每日摘要、" +
      "偵測到危急狀況時通知家人；資料會一直保留，開發團隊為了改善服務可檢視內容。" +
      "按下「建立長輩檔案」即代表您替長輩同意以上事項。",
    createElder: "建立長輩檔案",
    inviteHint: "長輩綁定碼（在長輩手機輸入或掃描一次即可）：",
    copyCode: "複製綁定碼",
    copied: "已複製",
    sendToElder: "送到左邊的長輩手機",
    empty: "還沒有長輩檔案，先在上面建立一位吧。",
    qrAlt: "長輩綁定用的 QR 圖",
  },
  elderDetail: {
    title: "長輩詳情",
    accountSaved: "已設定完成。長輩手機用這組號碼＋密碼登入一次就會一直記住。",
    accountSaveFailed: "設定失敗，請稍後再試。",
    inviteFailed: "產生邀請碼失敗",
    healthReportSection: "健康報告（近 30 天）",
    noRiskEvents: "沒有危急事件，一切平安。",
    remindersCount: (count: number) => `近 30 天提醒 ${count} 則`,
    dailySummarySection: "每日摘要",
    noSummaries: "還沒有摘要——長輩與金孫聊過天後，隔天早上就會出現。",
    schedulesSection: "全部行程",
    noSchedules: "還沒有任何提醒，點下方「管理行程」新增。",
    manageSchedules: "管理行程",
    accountSection: "長輩登入帳密（代辦）",
    accountHelp:
      "幫長輩設定手機號碼＋密碼。換手機或登出後，長輩用這組帳密登入即可，不用再掃碼；" +
      "忘記密碼時在這裡重設一次就好。",
    accountPhoneLabel: "長輩手機號碼",
    accountPhonePlaceholder: "09xxxxxxxx",
    accountPasswordLabel: "密碼（至少 8 碼）",
    saveAccount: "儲存帳密",
    inviteSection: "邀請其他家屬",
    makeInvite: "產生家屬邀請碼",
  },
  schedules: {
    title: "行程管理",
    confirmDelete: (title: string) => `確定要刪除「${title}」嗎？`,
    listSection: "全部行程",
    empty: "還沒有任何提醒，從下方新增第一筆。",
    editSection: "編輯提醒",
    addSection: "新增提醒",
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
    whenRequired: "請填寫提醒時間，格式請照欄位下方的範例。",
    editHint: "修改後請重新填一次提醒時間。",
    byElder: "（長輩自己交代的）",
    customTimePlaceholder: "07:30",
    confirmDeleteButton: "確定刪除",
  },
  notifications: {
    title: "通知",
    empty: "目前沒有通知。金孫有事會第一時間放在這裡。",
  },
};
