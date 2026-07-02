"""資料來源 ingestion 前的保守驗證。"""

from __future__ import annotations

from dataclasses import dataclass

from kinsun.rag.schemas import CopyrightStatus, RecommendedStatus, Source, TrustLevel


@dataclass(frozen=True)
class SourceValidationResult:
    source_id: str
    can_ingest: bool
    issues: tuple[str, ...]


class SourceValidator:
    def validate(self, source: Source) -> SourceValidationResult:
        issues: list[str] = []
        if not source.approved_for_rag:
            issues.append("來源尚未核准進入衛教 RAG。")
        if source.recommended_status != RecommendedStatus.APPROVED:
            issues.append(f"來源驗證狀態為 {source.recommended_status.value}。")
        if source.copyright_status != CopyrightStatus.ALLOWED:
            issues.append(f"授權狀態為 {source.copyright_status.value}。")
        if source.trust_level == TrustLevel.LOW:
            issues.append("來源可信度為 low。")
        if not source.allowed_domains:
            issues.append("缺少 crawler allowlist 網域。")
        return SourceValidationResult(
            source_id=source.source_id,
            can_ingest=len(issues) == 0,
            issues=tuple(issues),
        )
