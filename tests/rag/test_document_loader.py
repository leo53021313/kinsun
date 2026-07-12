"""文件載入：StaticDocumentLoader 依 id 取件，未知 id 明確失敗。"""

from __future__ import annotations

from datetime import date

import pytest

from kinsun.rag.document_loader import LoadedDocument, StaticDocumentLoader
from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CopyrightStatus,
    Language,
    MedicalScope,
    SourceType,
    TrustLevel,
)


def _doc(document_id: str) -> LoadedDocument:
    return LoadedDocument(
        text="高血壓照護包含規律量血壓。",
        metadata=ChunkMetadata(
            source_id="hpa_elder_health",
            document_id=document_id,
            chunk_id=f"{document_id}#chunk-1",
            title="高血壓衛教",
            publisher="衛生福利部國民健康署",
            source_url="https://www.hpa.gov.tw/demo",
            source_type=SourceType.GOVERNMENT,
            language=Language.ZH_TW,
            topic="高血壓",
            audience=Audience.ELDER,
            medical_scope=MedicalScope.HEALTH_EDUCATION,
            trust_level=TrustLevel.HIGH,
            approved_for_rag=True,
            copyright_status=CopyrightStatus.ALLOWED,
            source_published_at=date(2026, 1, 1),
            source_updated_at=None,
            retrieved_at=date(2026, 6, 30),
        ),
    )


def test_load_returns_document_by_id():
    loader = StaticDocumentLoader({"doc-1": _doc("doc-1")})
    loaded = loader.load("doc-1")
    assert loaded.metadata.document_id == "doc-1"
    assert "規律量血壓" in loaded.text


def test_load_unknown_id_raises_key_error():
    loader = StaticDocumentLoader({})
    with pytest.raises(KeyError):
        loader.load("doc-nope")
