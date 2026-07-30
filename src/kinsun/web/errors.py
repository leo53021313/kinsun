"""API 錯誤碼中央註冊（✅ 庚-25／A-56）：對外錯誤碼的唯一出處。

新增錯誤碼三步：
1. 此處加成員；
2. `envelope.ERROR_MESSAGES` 配繁中文案——有測試強制，漏配 CI 會紅；
3. `docs/dev/06_API設計規範.md` §3 錯誤碼表補列。

服務層例外（`InviteError`／`AppAccountError`）的 reason 屬領域內部詞彙，
在路由邊界翻成本表成員（如 `used` → `INVITE_USED`），不直接外流。
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    # --- 認證與授權 ---
    MISSING_TOKEN = "missing_token"
    INVALID_TOKEN = "invalid_token"
    # 框架層（打錯網址／方法不對）與排程業務驗證的統一出口（A-04／A-01，2026-07-29）
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    INVALID_SCHEDULE = "invalid_schedule"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_ADMIN_KEY = "invalid_admin_key"
    CONSENT_REVOKED = "consent_revoked"

    # --- 資源不存在 ---
    ELDER_NOT_FOUND = "elder_not_found"
    MEDICATION_NOT_FOUND = "medication_not_found"
    APPOINTMENT_NOT_FOUND = "appointment_not_found"
    TRACE_NOT_FOUND = "trace_not_found"
    SCHEDULE_NOT_FOUND = "schedule_not_found"
    JOB_NOT_FOUND = "job_not_found"
    # 這支 job 存在，但由別的程序執行（如 RAG 週更），後台無法就地觸發。
    JOB_NOT_RUNNABLE_HERE = "job_not_runnable_here"
    STRATEGY_NOT_FOUND = "strategy_not_found"
    CHUNK_NOT_FOUND = "chunk_not_found"

    # --- 分段語音串流（2026-07-26 延遲優化）---
    CHUNK_SUPERSEDED = "chunk_superseded"  # 那一輪已被新的一輪取代，App 應停止續拉
    SPEECH_UNAVAILABLE = "speech_unavailable"  # 合成或上傳失敗，後續段落取不到

    # --- 帳號 ---
    EMAIL_TAKEN = "email_taken"
    PHONE_TAKEN = "phone_taken"
    PASSWORD_TOO_SHORT = "password_too_short"
    INVALID_PHONE = "invalid_phone"
    NOT_PAIRED = "not_paired"

    # --- 邀請碼 ---
    INVITE_NOT_FOUND = "invite_not_found"
    INVITE_USED = "invite_used"
    INVITE_EXPIRED = "invite_expired"
    INVITE_WRONG_ROLE = "invite_wrong_role"
    TOO_MANY_ATTEMPTS = "too_many_attempts"

    # --- 輸入驗證 ---
    NAME_REQUIRED = "name_required"
    LABEL_REQUIRED = "label_required"
    SLOTS_REQUIRED = "slots_required"
    INVALID_SLOT = "invalid_slot"
    INVALID_KIND = "invalid_kind"
    KIND_NOT_CHANGEABLE = "kind_not_changeable"
    OCCURRENCES_REQUIRED = "occurrences_required"
    INVALID_DATE = "invalid_date"
    INVALID_TIME = "invalid_time"
    DATE_IN_PAST = "date_in_past"
    INVALID_STATUS = "invalid_status"
    INVALID_ACTION = "invalid_action"
    VALIDATION_ERROR = "validation_error"

    # --- 請求限制 ---
    TOO_MANY_REQUESTS = "too_many_requests"
    AUDIO_TOO_LARGE = "audio_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"

    # --- 維運 ---
    INTERNAL_TESTING_DISABLED = "internal_testing_disabled"
    ADMIN_DISABLED = "admin_disabled"
