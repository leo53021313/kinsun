from datetime import date

import pytest

from kinsun.rag.chunker import chunk_text
from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CopyrightStatus,
    Language,
    MedicalScope,
    SourceType,
    TrustLevel,
)


def _metadata() -> ChunkMetadata:
    return ChunkMetadata(
        source_id="hpa_faq",
        document_id="hpa-faq-1",
        chunk_id="placeholder",
        title="常見問答",
        publisher="衛生福利部國民健康署",
        source_url="https://www.hpa.gov.tw/example",
        source_type=SourceType.GOVERNMENT,
        language=Language.ZH_TW,
        topic="長者健康",
        audience=Audience.GENERAL_PUBLIC,
        medical_scope=MedicalScope.HEALTH_EDUCATION,
        trust_level=TrustLevel.HIGH,
        approved_for_rag=True,
        copyright_status=CopyrightStatus.ALLOWED,
        source_published_at=None,
        source_updated_at=None,
        retrieved_at=date(2026, 6, 29),
    )


def test_chunk_text_preserves_metadata_and_assigns_chunk_ids():
    chunks = chunk_text("第一段衛教。\n\n第二段衛教。", _metadata(), max_chars=80)

    assert len(chunks) == 1
    assert chunks[0].metadata.chunk_id == "hpa-faq-1#chunk-1"
    assert chunks[0].metadata.source_id == "hpa_faq"


def test_chunk_text_rejects_too_small_limit():
    with pytest.raises(ValueError):
        chunk_text("短文", _metadata(), max_chars=20)


def test_chunk_text_hard_splits_long_sentence_with_80_char_overlap():
    text = "甲" * 1500

    chunks = chunk_text(text, _metadata(), max_chars=700, overlap_chars=80)

    assert all(0 < len(chunk.text) <= 700 for chunk in chunks)
    assert chunks[0].text[-80:] == chunks[1].text[:80]


def test_chunk_text_splits_on_chinese_punctuation_and_newlines():
    chunks = chunk_text(
        "第一句；第二句？\n第三段！第四句。",
        _metadata(),
        max_chars=80,
    )

    assert "\n" in chunks[0].text
