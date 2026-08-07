/** App 端 UI 文案集中（✅ 庚-31／D-50）：依畫面分組；改文案只動此檔。
 * common 收跨畫面共用的通用文案（錯誤／狀態訊息、共用動作動詞、登入欄位）；
 * 其餘依畫面／區域分組。動態組字改為函式常數（見 elderDetail.remindersCount 等）。
 *
 * 2026-08 改版｜角色改名與人稱規則：
 *   阿白 = 角色（長輩對話的那隻北極熊），自述一律「我」。
 *   金孫 = 服務名（品牌字樣、App 名稱、同意條款主體），不改。
 *   第三人稱只在「系統描述角色」時用：狀態帶「阿白正在說話」、按鈕「請阿白再說一次」。
 *   家屬端一律第三人稱——家屬讀的是報告，不是對話。
 *   ⚠ LLM system prompt 與 TTS 要同步改，否則畫面說阿白、聲音說金孫。
 */
export const strings = {
  common: {
    loading: "載入中…",
    loadFailedShort: "載入失敗",
    loadFailed: "載入失敗，請稍後再試。",
    connectionFailed: "連線失敗，請稍後再試。",
    saveFailed: "儲存失敗，請稍後再試。",
    deleteFailed: "刪除失敗，請稍後再試。",
    cancel: "取消",
    delete: "刪除",
    edit: "編輯",
    create: "新增",
    update: "更新",
    retry: "再試一次",
    cancelEdit: "取消編輯",
    on: "開",
    off: "關",
    login: "登入",
    passwordLabel: "密碼",
    passwordPlaceholder: "至少 8 碼",
  },
  nav: {
    role: "選擇身分",
    guardianLogin: "家屬登入",
    guardianRegister: "家屬註冊",
    guardianHome: "我的長輩",
    elderDetail: "長輩詳情",
    schedules: "行程管理",
    dailySummary: "每日摘要",
    editAppointment: "改回診時間",
    criticalAlert: "危急詳情",
    notifications: "通知",
    elderBind: "輸入綁定碼",
    elderLogin: "長輩登入",
    // 新增（批次 4）：長輩端當天對話
    elderHistory: "之前聊過的",
  },
  guardianTabs: {
    home: "首頁",
    report: "報告",
    add: "新增提醒",
    addA11y: "新增用藥或回診提醒",
    notifications: "通知",
    profile: "阿公",
  },
  role: {
    brand: "金孫",                                   // 服務名，不改
    slogan: "聽懂國台語的長輩陪伴守護",
    iAmElder: "我是長輩",
    iAmGuardian: "我是家屬",
    switchToElder: "切換到長輩端（內測）",
    switchToGuardian: "切換到家屬端（內測）",
  },
  elderBind: {
    inviteNotFound: "找不到這組號碼，請跟家人再確認一次。",
    inviteUsed: "這組號碼已經用過了，請家人重新產生一組。",
    inviteExpired: "這組號碼過期了，請家人重新產生一組。",
    tooManyAttempts: "試太多次了，請家人重新產生一組。",
    bindFailed: "連不上金孫，請稍後再試一次。",       // 服務名：連不上的是服務
    cameraPermission: "需要相機權限才能掃描，也可以直接輸入號碼。",
    scanHint: "把家人給的方塊圖對準框框",
    switchToManual: "改用輸入號碼",
    hint: "掃描家人給的方塊圖，或輸入號碼",
    scanQr: "掃描方塊圖",
    codePlaceholder: "綁定碼",
    start: "開始使用",
    loginLink: "用過金孫？帳號密碼登入",             // 服務名
  },
  elderLogin: {
    notPaired: "這支手機還沒跟家人配對過，請先請家人給您方塊圖掃描一次。",
    wrongCredentials: "號碼或密碼不對，可以請家人幫忙確認。",
    hint: "輸入家人幫您設定的手機號碼和密碼，登入一次就會一直記住。",
    phoneLabel: "手機號碼",
  },
  talk: {
    screenTitle: "陪伴對話",
    companionTitle: "阿白在這裡",                    // 系統描述角色
    idleHint: "按住下面的麥克風說話，或按一下開始、說完再按一下",
    fallback: "我沒聽清楚，再說一次好嗎？",          // 阿白自述
    micPermission: "需要麥克風權限才能跟阿白說話，請到設定開啟。",
    listening: "我在聽…",                            // 阿白自述
    listeningTapHint: "我在聽…說完再按一下",
    thinking: "我想一下…",                           // 阿白自述
    bindingLost: "這台手機的綁定失效了，請家人重新給您一組號碼。",
    queued: (position: number) => `我還在忙，您現在排第 ${position} 位，輪到就馬上回您。`,
    pressToTalk: "按住說話，或按一下開始、再按一下結束",
    // 狀態帶：系統在描述角色，用第三人稱
    status: {
      idle: "準備好了",
      listening: "正在聽你說",
      thinking: "想一下喔",
      speaking: "阿白正在說話",
      error: "連線不太穩",
    },
    // 狀態副標：阿白自述，用第一人稱
    statusSub: {
      idle: "我在這裡等您",
      listening: "說完放開就好",
      thinking: "馬上就好",
      speaking: "聽完再按一下就好",
      error: "我暫時聽不到您說話",
    },
    actions: {
      start: "按住說話，或按一下開始",
      listening: "按住或放開",
      tapToSend: "說完再按一下",
      releaseToSend: "放開送出",
      thinking: "正在想",
      speaking: "正在說",
      retry: "再按一下重新說",
      // 新增（批次 3）：阿白說話時主鍵縮成 72dp 的標籤
      waitWhileSpeaking: "等阿白說完，再按這裡",
      replay: "請阿白再說一次",
    },
    // 新增（批次 3）：回話收合後的單行摘要
    collapsedPrefix: "剛才阿白說：",
    // 新增（批次 3）：健康類回答的出處，寫成人話不放連結
    sourceHealthEdu: "衛福部衛教資料的說法",
    // 新增（批次 3）：連線不穩時的兩個可行動作
    errorStep1: "走到窗邊或客廳，訊號比較好。",
    errorStep2: "還是不行，打電話給家人。",
    errorReassure: "您說的話我會先記著，接上就回您。",
    errorRetry: "再試一次",
    logout: "登出",
    logoutConfirmTitle: "登出",
    logoutConfirmBody: "確定要登出嗎？下次要用手機號碼和密碼再登入。",
    logoutCancel: "取消",
    debugMicLabel: "麥克風",
    debugLocationLabel: "定位",
    debugGranted: "已授權",
    debugDenied: "未授權",
  },
  // 新增（批次 4）：長輩端當天對話。只留當天，跟隨短期記憶的界線。
  elderHistory: {
    title: "之前聊過的",
    entryButton: "之前聊過的",
    youSaid: "您說：",
    bearSaid: "阿白說：",
    replay: "再聽一次",
    empty: "今天還沒聊過。按下面的麥克風跟我說說話吧。",
    footnote: "只留今天的，明天就換新的了。",
    back: "回去講話",
  },
  guardianLogin: {
    wrongCredentials: "帳號或密碼不對，請再試一次。",
    registerLink: "還沒有帳號？註冊",
    // 新增（批次 6）：底部先預告會有代為同意這件事
    consentPreview:
      "登入後才會看到長輩的對話內容。建立長輩檔案時會請您代為同意資料使用條款。",
  },
  guardianRegister: {
    passwordTooShort: "密碼至少 8 碼。",
    emailTaken: "這個 Email 已經註冊過了，請直接登入。",
    nameLabel: "您的稱呼",
    namePlaceholder: "例如：兒子小明",
    submit: "註冊並登入",
  },
  guardianHome: {
    nameRequired: "請先輸入長輩的稱呼。",
    addFailed: "新增失敗",
    logout: "登出",
    logoutConfirm: "確定要登出嗎？",
    notify: "通知",
    addElderSection: "新增長輩",
    elderNameLabel: "長輩稱呼",
    elderNamePlaceholder: "例如：阿公",
    // 同意條款的主體是服務，維持「金孫」不改
    consent:
      "建立後，金孫會記錄長輩與它的對話內容（文字與語音），用來陪伴關懷、產生每日摘要、" +
      " 偵測到危急狀況時通知家人；資料會一直保留，開發團隊為了改善服務可檢視內容。" +
      " 按下「建立長輩檔案」即代表您替長輩同意以上事項。",
    createElder: "建立長輩檔案",
    inviteHint: "長輩綁定碼（在長輩手機輸入或掃描一次即可）：",
    copyCode: "複製綁定碼",
    copiedTitle: "已複製",
    copiedMessage: "綁定碼已複製，可貼給家人或長輩。",
    empty: "還沒有長輩檔案，先在上面建立一位吧。",
    // 新增（批次 6）：首頁第一張卡永遠是今天
    todaySection: "今天",
    todayEmpty: "今天沒有要處理的事。",
    overdue: (minutes: number) => `還沒確認 · 已過 ${minutes} 分鐘`,
    askAgain: "請阿白再問一次",                      // 系統描述角色
    lastSpoke: "最後說話",
    mood: "心情",
  },
  elderDetail: {
    accountSaved: "已設定完成。長輩手機用這組號碼＋密碼登入一次就會一直記住。",
    accountSaveFailed: "設定失敗，請稍後再試。",
    inviteFailed: "產生邀請碼失敗",
    healthReportSection: "健康報告（近 30 天）",
    noRiskEvents: "沒有危急事件，一切平安。",
    remindersCount: (count: number) => `近 30 天提醒 ${count} 則`,
    dailySummarySection: "每日摘要",
    noSummaries: "還沒有摘要——長輩與阿白聊過天後，隔天早上就會出現。",
    schedulesSection: "全部行程",
    noSchedules: "還沒有任何提醒，點下方「管理行程」新增。",
    manageSchedules: "管理行程",
    viewDailySummaries: "查看每日摘要",
    accountSection: "長輩登入帳密（代辦）",
    accountHelp:
      "幫長輩設定手機號碼＋密碼。換手機或登出後，長輩用這組帳密登入即可，不用再掃碼；" +
      " 忘記密碼時在這裡重設一次就好。",
    accountPhoneLabel: "長輩手機號碼",
    accountPasswordLabel: "密碼（至少 8 碼）",
    saveAccount: "儲存帳密",
    inviteSection: "邀請其他家屬",
    makeInvite: "產生家屬邀請碼",
  },
  // 新增（批次 6）：每日摘要獨立畫面
  dailySummary: {
    title: "昨天的摘要",
    section: "這一天",
    prevDay: "看前一天",
    nextDay: "看後一天",
    disclaimer: "這是阿白整理的摘要，不是長輩的原話。",
    shareFailed: "無法開啟分享面板，請稍後再試。",
    saidSection: "長輩說的話",
    saidNote: "原話照登，阿白不改寫、不美化。",
    noticedSection: "阿白注意到的",
    noticedDisclaimer: "這是阿白注意到的關聯，不是診斷。",
    daySection: "這一天",
    share: "傳這份摘要給家人",
  },
  // `driver`／`notify_elder` 尚未進入 ScheduleInput 與後端契約；文案先保留，畫面暫不顯示。
  editAppointment: {
    whenLabel: "新的日期與時間",
    whenHint: "改完記得也跟醫院改掛號——阿白不會幫您打電話。",
    invalidWhen: "請用「西元年-月-日 時:分」填寫，時間可以省略。",
    notFound: "找不到這筆回診行程，可能已被刪除。",
    driverLabel: "誰帶長輩去",
    tellElderLabel: "讓阿白告訴長輩改了",
    tellElderHelp: "下次他開口說話時說一句「回診改到 8/19」。",
    elderSeesOnlyNewTime: "長輩那端只會聽到新的時間，不會看到「誰改的、改過幾次」。",
    savedEffect: "存檔後，後續提醒會改用新的時間；阿白不會替您聯絡醫院改掛號。",
    save: "存起來",
    deleteTitle: "刪除回診行程",
    deleteConfirm: (title: string) => `確定要刪除「${title}」嗎？`,
    deleteThis: "刪除這個行程",
  },
  // 新增（批次 6）：危急通知詳情
  criticalAlert: {
    badge: "危急通知　需要您處理",
    unhandled: "危急通知　還沒有人處理",
    recordingSection: "當時的錄音",
    transcriptSection: "當時的對話",
    noJudgement: "阿白沒有判斷是什麼病，只做了兩件事：讓長輩坐下、通知您。",
    deliverySection: "通知送給了誰",
    callElder: "打電話給長輩",
    handled: "我處理好了",
    notCritical: "這不算危急",
    safeFallbackTitle: "危急詳情尚未連線",
    safeFallbackBody:
      "目前不會顯示錄音或逐字對話。完成危急詳情端點、重新同意與查閱稽核後，才會開放這些內容。",
    reasonLabel: "事件原因",
    reasonUnavailable: "後端尚未提供這筆事件的原因。",
    timeLabel: "發生時間",
    timeUnavailable: "後端尚未提供這筆事件的時間。",
  },
  schedules: {
    deleteTitle: "刪除提醒",
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
    // 新增（批次 6）：兩步流程
    stepOf: (n: number, total: number) => `第 ${n} 步，共 ${total} 步`,
    nameHelp: "阿白會用這個名字問長輩，寫他聽得懂的說法就好。",
    willSpeakLabel: "讓阿白開口問一句",
    willSpeakHelp: "時間到會主動說「阿公，該吃藥了」。",
    step2Title: "長輩沒回應的時候",
    retryLabel: "阿白先再問一次",
    retryHelp: "30 分鐘後用同樣的口氣問長輩。",
    escalateLabel: "還是沒回應就通知我",
    escalateHelp: "出現在您的首頁與通知頁，不會打擾長輩。",
    ruleSection: "這條提醒會這樣跑",
    elderWillSee: (guardianName: string) =>
      `長輩會看到「這件事是家裡的${guardianName}幫您記下來的」。`,
    submit: "建立這條提醒",
  },
  notifications: {
    empty: "目前沒有通知。阿白有事會第一時間放在這裡。",
  },
  // 長輩看的提醒（X-01，2026-07-29）：用詞比家屬版更白話，不用「通知」這個詞。
  elderNotifications: {
    title: "阿白的提醒",
    empty: "現在沒有要提醒您的事。時間到了我會跟您說。",  // 阿白自述
    back: "回去講話",
    bell: "看阿白的提醒",
    // 新增（批次 3）：單題確認畫面
    doneAnswer: "吃過了",
    laterAnswer: "還沒，等一下吃",
    ackAnswer: "知道了",
    cannotGoAnswer: "那天我沒辦法去",
    setByFamily: (name: string) => `${name}幫您記下來的`,
    bubbleMedication: (name: string) => `${name}請我提醒您`,
    statusPending: "還沒做",
    statusDone: "已完成",
    statusUpcoming: "後天要出門",
    footnote: "都是家人幫您記下來的。",
  },
} as const;
