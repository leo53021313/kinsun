"""衛教 RAG 的核心資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

RAG_EMBEDDING_DIMENSIONS = 768


class SourceType(StrEnum):
    GOVERNMENT = "government"
    HOSPITAL = "hospital"
    MEDICAL_ASSOCIATION = "medical_association"
    GUIDELINE = "guideline"
    ACADEMIC = "academic"
    INTERNATIONAL_OFFICIAL = "international_official"
    OTHER = "other"


class Language(StrEnum):
    ZH_TW = "zh-TW"
    EN = "en"
    MIXED = "mixed"


class Audience(StrEnum):
    ELDER = "elder"
    CAREGIVER = "caregiver"
    GENERAL_PUBLIC = "general_public"


class MedicalScope(StrEnum):
    HEALTH_EDUCATION = "health_education"
    EMERGENCY_WARNING = "emergency_warning"
    MEDICATION = "medication"
    CHRONIC_DISEASE = "chronic_disease"
    PREVENTION = "prevention"
    NUTRITION = "nutrition"
    EXERCISE = "exercise"
    MENTAL_HEALTH = "mental_health"
    OTHER = "other"


class TrustLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CopyrightStatus(StrEnum):
    ALLOWED = "allowed"
    NEEDS_REVIEW = "needs_review"
    DISALLOWED = "disallowed"


class RecommendedStatus(StrEnum):
    APPROVED = "approved"
    CONDITIONAL = "conditional"
    REJECTED = "rejected"
    OUT_OF_SCOPE = "out_of_scope"


class SourceRole(StrEnum):
    """來源在 RAG 管線中的用途。discovery 只找更新，不直接支撐回答。"""

    ANSWER = "answer"
    DISCOVERY = "discovery"


class ContentPolicy(StrEnum):
    """內容授權政策；classroom_demo 僅供非商用課堂展示。"""

    ALLOWED_ONLY = "allowed_only"
    CLASSROOM_DEMO = "classroom_demo"


class SafetyLevel(StrEnum):
    NORMAL = "normal"
    CAUTION = "caution"
    URGENT = "urgent"
    UNSUPPORTED = "unsupported"


class CrawlStatus(StrEnum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    url: str
    publisher: str
    source_type: SourceType
    trust_level: TrustLevel
    copyright_status: CopyrightStatus
    recommended_status: RecommendedStatus
    approved_for_rag: bool
    allowed_domains: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""
    role: SourceRole = SourceRole.ANSWER
    # 內容頁（文章）的網址樣式（regex），留空＝一視同仁。兩個用途：
    # ①待爬清單優先抓文章，不把預算耗在導覽與列表頁（2026-07-30 實測：爬 885 頁
    #   只換到 58 篇文章）；②從 sitemap 取清單時，用來濾掉列表頁只留文章頁。
    # 註：曾經還有第三個用途「導覽區的連結若符合本樣式就破例收錄」，2026-08-01
    #     實測推翻並移除，理由見 crawler.HtmlTextExtractor.handle_starttag 的註解。
    content_url_pattern: str = ""
    # 站台 sitemap.xml 的網址，有值就改用「讀清單」取代「爬連結」。
    # 爬連結對 hpa 這種每頁都渲染全站選單（225 個分類連結）的網站必然主題漂移：
    # 2026-08-01 實測，三個不同主題的來源收回來的文章落在同一批 nodeid，全是頁尾
    # 共用連結。sitemap 一次給出 5,667 篇文章且每篇都標好分類，沒有猜測空間。
    sitemap_url: str = ""


@dataclass(frozen=True)
class RagDocument:
    document_id: str
    source_id: str
    url: str
    title: str
    publisher: str
    text: str
    content_hash: str
    source_type: SourceType
    language: Language
    topic: str
    audience: Audience
    medical_scope: MedicalScope
    trust_level: TrustLevel
    copyright_status: CopyrightStatus
    published_at: date | None
    updated_at: date | None
    retrieved_at: date


@dataclass(frozen=True)
class ChunkMetadata:
    source_id: str
    document_id: str
    chunk_id: str
    title: str
    publisher: str
    source_url: str
    source_type: SourceType
    language: Language
    topic: str
    audience: Audience
    medical_scope: MedicalScope
    trust_level: TrustLevel
    approved_for_rag: bool
    copyright_status: CopyrightStatus
    source_published_at: date | None
    source_updated_at: date | None
    retrieved_at: date
    last_reviewed_at: date | None = None
    version: str | None = None
    source_role: SourceRole = SourceRole.ANSWER


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    metadata: ChunkMetadata


@dataclass(frozen=True)
class SearchResult:
    chunk: DocumentChunk
    score: float
    matched_terms: tuple[str, ...] = field(default_factory=tuple)
    retrieval_method: str = "keyword"


@dataclass(frozen=True)
class Citation:
    source_id: str
    title: str
    publisher: str
    url: str
    chunk_id: str


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    safety_level: SafetyLevel
    citations: tuple[Citation, ...]
    requires_safety_attention: bool
    reason: str
    evidence: tuple[SearchResult, ...] = ()


@dataclass(frozen=True)
class IngestionAuditLog:
    source_id: str
    fetched_at: datetime
    content_hash: str
    chunk_count: int
    parser_used: str
    status: str
    error_message: str | None
    operator_or_job_id: str


@dataclass(frozen=True)
class IngestionSummary:
    source_id: str
    document_count: int
    chunk_count: int
    skipped_count: int
    failed_count: int
