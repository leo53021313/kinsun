/**
 * zh-TW 字串常數集中（沿用 ✅ D-50：不導入 i18n 框架，單語系）。
 *
 * 為什麼後端不直接回中文狀態文字：後端回的是機器可讀的狀態碼，文案歸前端。
 * 這樣改一句話不必動後端、不必重啟服務——展示前一天要改文案是常態。
 */

/**
 * 鈴鐺的用途說明。`elderNotifications.bell` 與 `bellWithUnread` 都要用到它，
 * 抽成常數而非兩處各寫一次同樣的字面值——兩處寫死的話，改一處就會漂。
 */
const ELDER_BELL_LABEL = "看金孫的提醒";

export const strings = {
  common: {
    loading: "載入中…",
    loadFailed: "載入失敗，請稍後再試。",
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
    // 長輩端對講機／提醒畫面接線前的暫時佔位文字（P3 Task 8／9 接上後這個分支
    // 就不會再被走到）；元件裡不可出現裸中文字串，即使只是暫時性的畫面也一樣。
    comingSoon: "這裡還在準備，請再等一下。",
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
    accountSaved: "已設定完成。長輩手機用這組號碼＋密碼登入一次就會一直記住。",
    accountSaveFailed: "設定失敗，請稍後再試。",
    inviteFailed: "產生邀請碼失敗",
    healthReportSection: "健康報告（近 30 天）",
    noRiskEvents: "沒有危急事件，一切平安。",
    remindersCount: (count: number) => `近 30 天提醒 ${count} 則`,
    dailySummarySection: "每日摘要",
    noSummaries: "還沒有摘要——長輩與金孫聊過天後，隔天早上就會出現。",
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
    bindingSection: "長輩手機綁定",
    bindingHelp: "長輩換手機、或手機不見了，在這裡重新產生一組綁定碼給他重新綁定。",
    // ⚠️ 這是不可逆的破壞性操作，後果要寫在按鈕**上面**、按下去之前就看得到。
    // 另外要把它跟「產生家屬邀請碼」講清楚——兩個都是「產生一組碼」，但一個會
    // 把長輩登出、一個不會。
    bindingWarning:
      "注意：一產生新碼，長輩目前手機上的金孫就會被登出，他要用新碼重綁一次才能" +
      "再跟金孫說話。只是想邀請另一位家屬看資料的話，請用下面的「產生家屬邀請碼」。",
    regenerateBinding: "重新產生長輩綁定碼",
    // ⚠️ 確認列講**後果**、不講動作：「確定要重新產生嗎」只是把按鈕字樣抄一遍，
    // 家屬看了還是不知道自己要換掉什麼。刪一筆排程都要二次確認了，這個會把長輩
    // 手機上的金孫直接登出的操作更需要——而且他按下去的當下，長輩可能正在講話。
    confirmRegenerateBinding:
      "長輩手機上的金孫會馬上被登出，他要用新的綁定碼重綁一次才能再跟金孫說話。確定要換嗎？",
    confirmRegenerateBindingButton: "確定換新碼",
    bindingFailed: "重新產生綁定碼失敗，請稍後再試。",
    inviteSection: "邀請其他家屬",
    makeInvite: "產生家屬邀請碼",
  },
  schedules: {
    // 帶長輩稱呼：家屬管兩位以上長輩時，光是「行程管理」四個字沒有告訴他正在編誰的。
    title: (elderName: string) => `${elderName}的行程管理`,
    confirmDelete: (title: string) => `確定要刪除「${title}」嗎？`,
    /** 長輩詳情頁的行程摘要區塊也用這一把——同一個概念不要兩把鍵。 */
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
  // 長輩端文案逐字沿用 app/src/lib/strings.ts 的既有措辭：口語敘述一律用
  // 「號碼」「方塊圖」，比「通知」「綁定」更白話；`codePlaceholder`（輸入框
  // 精簡提示）與逐字沿用的 `notPaired`／`bindingLost` 仍帶「綁定」二字，是
  // App 既有例外、非本輪新增。⚠️ `codeLabel`（P3 Task 7 新增，App 版沒有
  // 對應鍵——App 用畫面標題當標籤，網頁版才需要獨立的欄位標籤）**刻意不**
  // 跟進本段其餘欄位偏好的「號碼」措辭，仍用「綁定碼」：這是**一直掛在畫面
  // 上、讀螢幕軟體逐欄朗讀時會唸出來的可見標籤**，與提示文字（讀過就過）
  // 性質不同——長輩若先切去用過帳密登入（`elder/LoginScreen.tsx` 的欄位是
  // 「手機號碼」）再切回來，兩個畫面的標籤都只寫「號碼」會混淆是哪一種號碼；
  // 「綁定碼」在此處是必要的消歧，非疏漏。並補上網頁端獨有的幾條：
  // receivedFromGuardian／queued／micUnsupported（App 沒有這幾種情境，見 talk 段）；
  // `inviteWrongRole`（P3 Task 7）＋`cameraNotFound`／`cameraInUse`／
  // `cameraInsecureOrigin`／`cameraNoSignal`（P3 Task 7，對應 `talk/qrScanner.ts`
  // 的 `QrScannerError` 六種分類——App 端走 `expo-camera` 原生殼，沒有這麼細的
  // 瀏覽器相機錯誤分類）。
  elderBind: {
    inviteNotFound: "找不到這組號碼，請跟家人再確認一次。",
    inviteUsed: "這組號碼已經用過了，請家人重新產生一組。",
    inviteExpired: "這組號碼過期了，請家人重新產生一組。",
    tooManyAttempts: "試太多次了，請家人重新產生一組。",
    // 家屬把自己的邀請碼給長輩掃／打時會走到這裡（後端 409 invite_wrong_role）。
    // 這與「查無此碼」「已過期」完全是另一回事，混在一起講會讓長輩對著同一組碼
    // 反覆試——直接說清楚這組碼本來就不是給他用的。
    inviteWrongRole: "這組號碼是給家人用的，請家人給您長輩專用的那組。",
    bindFailed: "連不上金孫，請稍後再試一次。",
    cameraPermission: "需要相機權限才能掃描，也可以直接輸入號碼。",
    cameraUnsupported: "這個瀏覽器不能用相機，請直接輸入號碼。",
    cameraNotFound: "這台裝置沒有相機，請直接輸入號碼。",
    cameraInUse: "相機正被別的畫面用著，請直接輸入號碼，或關掉其他用相機的畫面再試一次。",
    // ⚠️ 不可講「換一家瀏覽器」：真正原因是網址不是安全來源（非 https 且非
    // localhost），常見於組員用區網 IP（如 http://192.168.x.x）連線；換瀏覽器
    // 解決不了，換網址才有用。
    cameraInsecureOrigin: "這個網址不能用相機，請改用家人給您、開頭是 https 的網址，或直接輸入號碼。",
    cameraNoSignal: "相機看不到畫面，請確認鏡頭沒被遮住，或直接輸入號碼。",
    scanHint: "把家人給的方塊圖對準框框",
    switchToManual: "改用輸入號碼",
    hint: "掃描家人給的方塊圖，或輸入號碼",
    scanQr: "掃描 QR 碼",
    codeLabel: "綁定碼",
    codePlaceholder: "綁定碼",
    start: "開始使用",
    loginLink: "用過金孫？帳號密碼登入",
    // 網頁端獨有：兩欄舞台的長輩欄可以直接看到家屬欄產生的碼，App 沒有這個情境。
    // ⚠️ 不寫死方位：`lg` 以下是頁籤擇一顯示（見 stage/StagePage.tsx），家屬欄
    // 不一定在畫面上，「右邊」在窄螢幕（組員拿手機自測）是錯的方向指示。
    // 沿用本段其餘欄位的口語用字「號碼」，不用「綁定碼」。
    receivedFromGuardian: "已從家屬手機收到號碼",
  },
  elderLogin: {
    notPaired: "這支手機還沒跟家人配對過，請先請家人給您綁定圖（QR）掃描一次。",
    wrongCredentials: "號碼或密碼不對，可以請家人幫忙確認。",
    hint: "輸入家人幫您設定的手機號碼和密碼，登入一次就會一直記住。",
    phoneLabel: "手機號碼",
  },
  talk: {
    idleHint: "按住下面的麥克風說話，或按一下開始、說完再按一下",
    fallback: "金孫沒聽清楚，再說一次好嗎？",
    micPermission: "需要麥克風權限才能跟金孫說話，請到設定開啟。",
    listening: "金孫在聽…",
    listeningTapHint: "金孫在聽…說完再按一下",
    thinking: "金孫想一下…",
    bindingLost: "這台手機的綁定失效了，請家人重新給您一組號碼。",
    pressToTalk: "按住說話，或按一下開始、再按一下結束",
    logout: "登出",
    logoutConfirmTitle: "登出",
    // ⚠️ 這顆確認鍵存在的理由，正是「家屬**還沒替他設過帳密**的長輩一按就自己
    // 回不來」——文案卻叫他用一組可能不存在的帳密，他會安心地按下確定，然後在
    // 登入畫面試一組不存在的密碼。前端無從得知帳密設過沒有，不能分支，但可以
    // 誠實地把另一條路一起講出來。
    logoutConfirmBody:
      "確定要登出嗎？下次要用手機號碼和密碼登入，還沒設過的話要請家人重新給您一組號碼。",
    logoutCancel: "取消",
    // 內測專用權限狀態列（僅 internalTesting 顯示）
    debugMicLabel: "麥克風",
    debugLocationLabel: "定位",
    debugGranted: "已授權",
    debugDenied: "未授權",
    // 網頁端獨有：容量閘門排隊位置（App 對應畫面待 P3 續行時另接）與瀏覽器錄音
    // 不支援的提示（App 是原生殼，不會遇到瀏覽器不支援錄音的情況）。
    // ⚠️ `position` 是排隊名次（1-based），不是「前面還有幾位」——正式環境併發
    // 上限 > 1 時，排隊名次 1 的人前面其實還有好幾輪正在跑、只是不在佇列裡
    // （見 channels/app/ws.py 與 06_API設計規範 §5 的既有裁決）。故不報「前面
    // 還有幾位」，改講排隊名次本身。
    queued: (position: number) => `金孫正在跟別人說話，您排第 ${position} 位…`,
    micUnsupported: "這個瀏覽器不能錄音，請換 Chrome、Safari 或 Firefox。",
    // ⚠️ 麥克風拿不到有好幾種成因，長輩要做的下一步完全不同（P3 Task 8 補齊，
    // 對應 `talk/recorder.ts::MicrophoneProbeResult` 的六種結果）。一律講「請到
    // 設定開啟」的話，沒有麥克風的桌機、用區網 IP 連進來的組員，都會去找一個
    // 根本不存在的權限開關——這與 Task 5／7 對相機做過的擴充是同一件事。
    micNotFound: "這台裝置沒有麥克風，請換一台有麥克風的手機或平板。",
    micInUse: "麥克風正被別的畫面用著，請把其他在錄音或講電話的畫面關掉再試一次。",
    // ⚠️ 不可講「換一家瀏覽器」：真正原因是網址不是安全來源（非 https 且非
    // localhost），常見於組員用區網 IP（如 http://192.168.x.x）連線。措辭與
    // `elderBind.cameraInsecureOrigin` 一致。
    micInsecureOrigin: "這個網址不能錄音，請改用家人給您、開頭是 https 的網址。",
    // 權限有了、但這一次就是打不開（裝置忙、系統把麥克風收走）。與
    // `fallback`（「金孫沒聽清楚」）刻意分開：錄音根本沒開始，說「沒聽清楚」
    // 會讓長輩以為是自己講得不夠大聲，於是一次比一次更用力喊。
    micStartFailed: "麥克風打不開，請再按一次試試看。",
    // 送出了、卻等不到任何回應（連線斷在半路、後端那一輪掉了）。⚠️ 沒有這條
    // 保險的話，畫面會永遠停在「金孫想一下…」而麥克風鍵一直是停用的——長輩
    // 從此按不動，也不知道發生什麼事。
    noAnswer: "金孫這次沒有回話，再說一次好嗎？",
    // 虛擬形象的可讀說明（讀螢幕軟體會唸出來；畫面上只有一個表情符號）。
    avatar: {
      idle: "金孫現在在等您說話",
      listening: "金孫現在在聽",
      thinking: "金孫現在在想",
      speaking: "金孫現在在說話",
    },
    confirmLogoutButton: "確定登出",
  },
  // 長輩看的提醒（X-01，2026-07-29）：用詞比家屬版更白話，不用「通知」這個詞。
  elderNotifications: {
    title: "金孫的提醒",
    empty: "現在沒有要提醒您的事。時間到了金孫會跟您說。",
    back: "回去講話",
    bell: ELDER_BELL_LABEL,
    // 讀螢幕的人聽不到紅色數字，未讀數必須進可及名稱裡（App 端同一套作法）。
    bellWithUnread: (count: number) => `${ELDER_BELL_LABEL}，${count} 則新的`,
  },
};
