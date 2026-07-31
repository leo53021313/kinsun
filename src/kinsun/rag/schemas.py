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
    #   只換到 58 篇文章）；②導覽區塊的連結原則上不收，但符合本樣式者例外——
    #   hpa 把文章連結放在 nav／header／footer（列表頁 37 個文章連結有 29 個在那），
    #   一律不收會把文章一起砍掉。
    content_url_pattern: str = ""


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
