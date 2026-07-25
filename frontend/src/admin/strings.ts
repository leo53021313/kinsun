/** 觀測後台 UI 文案集中（✅ 庚-31／D-50）：改文案只動此檔。 */

export const strings = {
  // 跨頁共用文案
  common: {
    loading: "載入中…",
    disconnected: "連線中斷，重試中…",
    loadFailedRefresh: "載入失敗，請重新整理。",
    refresh: "重新整理",
    viewTrace: "檢視鏈路",
    roleElder: "長輩",
    roleAssistant: "金孫",
  },

  // App 殼層（金鑰輸入頁＋導覽列）
  app: {
    title: "金孫 觀測後台",
    keyPlaceholder: "請輸入管理金鑰",
    enter: "進入",
    nav: {
      overview: "總覽",
      messages: "訊息流",
      elders: "長輩",
      news: "新聞",
      system: "系統",
    },
  },

  // 總覽儀表板
  overview: {
    title: "總覽儀表板",
    noRecentMessages: "近 24 小時沒有訊息。",
    hourlyChartAriaLabel: "近 24 小時逐時訊息量",
    hourBarTitle: (hour: number, count: number) => `${hour} 時：${count} 則`,
    guardianNotificationFailure: (windowMinutes: number, count: number) =>
      `⚠ 最近 ${windowMinutes} 分鐘有 ${count} 則危急通知送不到家屬——家屬可能漏收警報，請至長輩詳情頁的「危急通知」查明並主動聯絡。`,
    riskClassifierFailure: (windowMinutes: number, count: number) =>
      `⚠ 危急分級器最近 ${windowMinutes} 分鐘故障 ${count} 次——AI 分級可能失效、只剩關鍵詞守門，請排查 Gemini 連線（失敗句已保守記 L1 留痕）。`,
    stageLabel: {
      asr: "ASR",
      // LLM 逐種類分列（2026-07-25）：一輪多筆呼叫且快慢差一個量級，混在一起的
      // 百分位數沒有意義，故不再有單一「LLM」列。
      "llm:agent": "LLM｜回覆生成",
      "llm:risk_classify": "LLM｜危急分級",
      "llm:moderation": "LLM｜濫用審核",
      "llm:unknown": "LLM｜未分類（舊資料）",
      tts: "TTS",
      round_trip: "往返（端到端）",
    } as Record<string, string>,
    statTurnCount: "今日訊息量",
    statActiveElders: "活躍長輩",
    statRiskEvents: "風險事件",
    statLlmTokens: "LLM token（入／出）",
    stagesHeading: "各階段今日狀況",
    stageColumns: {
      stage: "階段",
      count: "次數",
      error: "錯誤",
      avgLatency: "平均延遲",
      p50Latency: "p50 延遲",
      p95Latency: "p95 延遲",
    },
    hourlyHeading: "近 24 小時訊息量",
    updatedAtPrefix: "更新於",
  },

  // 全域訊息流
  messages: {
    title: "全域訊息流",
    noMessages: "目前沒有訊息。",
    kindLabel: {
      turn: "對話",
      reminder: "推播",
      risk: "風險",
    } as Record<string, string>,
    tierPrefix: "等級",
    loadOlder: "載入更早的訊息",
  },

  // 長輩清單
  elders: {
    title: "長輩清單",
    noElders: "目前沒有長輩資料。",
    boundChannels: (channels: string) => `通道：${channels}`,
    notBound: "尚未綁定",
    lastActive: (time: string) => `最後活動 ${time}`,
    noConversation: "尚無對話",
  },

  // 話題新聞（D-74 消費端）
  news: {
    title: "話題新聞",
    daysLabel: "顯示範圍",
    daysOption: (days: number) => `近 ${days} 天`,
    empty: "這段期間沒有爬到新聞。爬蟲排程在每天凌晨；也可到「系統」頁手動執行 news-crawl。",
    note: "新聞由每日排程爬取（衛福部；News API 需金鑰），供金孫問候與聊天當話題素材；逾期自動清除。",
    columns: {
      retrievedAt: "抓取時間",
      source: "來源",
      publisher: "媒體",
      title: "標題",
      publishedAt: "發布時間",
    },
    unknownPublishedAt: "未提供",
  },

  // 系統排程
  system: {
    title: "系統排程",
    rag: {
      heading: "衛教 RAG 索引",
      active: "目前版本",
      latest: "最近更新",
      none: "尚無",
      policy: "內容政策",
      counts: (documents: number, chunks: number) =>
        `文件 ${documents} 份／chunk ${chunks} 段`,
    },
    runFailed: "執行失敗，請確認內測模式是否開啟。",
    jobExecuted: (jobName: string) => `已執行 ${jobName}。`,
    columns: {
      job: "任務",
      cron: "排程（cron）",
      lastRun: "上次執行",
      action: "操作",
    },
    neverRun: "尚未執行",
    running: "執行中…",
    runNow: "立即執行（內測）",
    manualRunNote: "手動執行不會更新「上次執行」（不干擾排程器的到期判斷）。",
  },

  // 長輩時間軸
  timeline: {
    fallbackTitle: "長輩時間軸",
    title: (name: string) => `${name} 的時間軸`,
    dateLabel: "日期：",
    noRecords: "這一天沒有任何紀錄。",
    voice: "語音",
    reminderBadge: "推播",
    riskPrefix: "風險",
  },

  // 單輪處理鏈路
  trace: {
    title: "單輪處理鏈路",
    notFound: "找不到這一輪的鏈路資料。",
    statusOk: "成功",
    statusFail: "失敗",
    openInOpik: "在 Opik 開啟",
    steps: {
      webhook: "1. Webhook 收到",
      asr: "2. ASR 辨識",
      rag: "3. 衛教 RAG 檢索",
      llm: "4. LLM 生成",
      tts: "5. TTS 合成",
      reply: "6. 回覆送出",
      risk: "風險事件",
    },
    typeLabel: "類型：",
    rawPayload: "原始 payload",
    noRecord: "沒有紀錄。",
    asrTranscript: "辨識結果：",
    llmTokens: (input: number, output: number | null) => `　token 入 ${input}／出 ${output}`,
    llmReply: "回覆：",
    ragQuery: "查詢：",
    ragRelease: "索引版本：",
    ragReason: "判定：",
    ragHits: "檢索命中",
    ragCitations: "完整引用",
    replyKindLabel: "形式：",
    replyVoice: "語音",
    replyText: "文字",
  },

  // 長輩詳情分頁
  elderTabs: {
    tabs: {
      timeline: "時間軸",
      reminders: "提醒設定",
      memory: "記憶與摘要",
      account: "帳號與綁定",
      risk: "危急通知",
    },
    account: {
      bindingsHeading: "綁定通道",
      noBindings: "尚未綁定任何通道。",
      boundAtPrefix: "綁定於",
      accountHeading: "帳號",
      passwordAccount: (phone: string | null) => `已設定帳密登入（手機：${phone}）`,
      noPasswordAccount: "尚未設定帳密登入（家屬可在 App 代辦）",
      validTokenLine: (count: number) => `｜有效 token：${count} 個`,
      invitesHeading: "邀請碼",
      noInvites: "沒有邀請碼紀錄。",
      inviteRoleElder: "長輩綁定碼",
      inviteRoleGuardian: "家屬邀請碼",
      inviteStatus: {
        active: "有效",
        used: "已使用",
        expired: "已過期",
        locked: "已鎖定（嘗試次數用完）",
      } as Record<string, string>,
      inviteMeta: (expiresAt: string, attempts: number) =>
        `到期 ${expiresAt}｜已嘗試 ${attempts} 次`,
      consentHeading: "同意紀錄",
      consentRecord: (p: {
        isProxy: boolean;
        version: string;
        grantedAt: string;
        revokedAt: string | null;
      }) =>
        `${p.isProxy ? "家屬代辦" : "本人"}同意（版本 ${p.version}）於 ${p.grantedAt}${
          p.revokedAt ? `；已於 ${p.revokedAt} 撤回` : ""
        }`,
      noConsent: "尚無同意紀錄",
      guardiansHeading: "家屬連結",
      noGuardians: "尚無家屬連結。",
      escalationPrefix: "升級順位",
    },
    memory: {
      longTermHeading: "長期記憶（AI 記住的事）",
      noMemories: "還沒有長期記憶。",
      dailySummaryHeading: "每日對話摘要",
      noSummaries: "還沒有摘要。",
    },
    reminders: {
      slotLabels: {
        morning: "早上",
        noon: "中午",
        evening: "晚上",
        bedtime: "睡前",
      } as Record<string, string>,
      dispatchTriggered: "已觸發發送，可到時間軸或訊息流確認。",
      dispatchFailed: "觸發失敗，請確認內測模式是否開啟。",
      scheduleHeading: "提醒設定",
      noSchedules: "尚未設定任何提醒。",
      byElder: "長輩自己交代",
      kindLabels: {
        medication: "吃藥",
        appointment: "回診",
        custom: "其他",
      } as Record<string, string>,
      sendKindButton: (kindLabel: string) => `立即發送${kindLabel}提醒（內測）`,
      logsHeading: "近期提醒發送紀錄",
      noLogs: "還沒有發送紀錄。",
    },
    risk: {
      deliveryFailed: "失敗",
      deliveryInbox: "已入通知匣（待開啟）",
      deliveryDelivered: "送達",
      heading: "危急通知送達紀錄（每位家屬一筆）",
      noNotifications: "還沒有危急通知。",
      notifyPrefix: "通知",
    },
  },
} as const;
