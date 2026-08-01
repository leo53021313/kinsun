from datetime import date

import pytest

from kinsun.rag.answer_policy import AnswerPolicy
from kinsun.rag.keyword_index import InMemoryKeywordIndex
from kinsun.rag.retriever import HealthEducationRetriever, extract_keyword_terms
from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CopyrightStatus,
    DocumentChunk,
    Language,
    MedicalScope,
    SafetyLevel,
    SourceRole,
    SourceType,
    TrustLevel,
)


def _metadata(
    *,
    source_id: str = "hpa_health_education",
    chunk_id: str = "doc-1#chunk-1",
    title: str = "高血壓衛教",
    topic: str = "高血壓",
    approved_for_rag: bool = True,
    copyright_status: CopyrightStatus = CopyrightStatus.ALLOWED,
    source_role: SourceRole = SourceRole.ANSWER,
) -> ChunkMetadata:
    return ChunkMetadata(
        source_id=source_id,
        document_id="doc-1",
        chunk_id=chunk_id,
        title=title,
        publisher="衛生福利部國民健康署",
        source_url="https://www.hpa.gov.tw/example",
        source_type=SourceType.GOVERNMENT,
        language=Language.ZH_TW,
        topic=topic,
        audience=Audience.ELDER,
        medical_scope=MedicalScope.HEALTH_EDUCATION,
        trust_level=TrustLevel.HIGH,
        approved_for_rag=approved_for_rag,
        copyright_status=copyright_status,
        source_published_at=date(2026, 1, 1),
        source_updated_at=date(2026, 1, 1),
        retrieved_at=date(2026, 6, 29),
        last_reviewed_at=date(2026, 6, 29),
        source_role=source_role,
    )


def _chunk(
    text: str,
    *,
    source_id: str = "hpa_health_education",
    chunk_id: str = "doc-1#chunk-1",
    topic: str = "高血壓",
    approved_for_rag: bool = True,
    copyright_status: CopyrightStatus = CopyrightStatus.ALLOWED,
    source_role: SourceRole = SourceRole.ANSWER,
) -> DocumentChunk:
    return DocumentChunk(
        text=text,
        metadata=_metadata(
            source_id=source_id,
            chunk_id=chunk_id,
            topic=topic,
            approved_for_rag=approved_for_rag,
            copyright_status=copyright_status,
            source_role=source_role,
        ),
    )


def test_retriever_keeps_license_metadata_but_requires_rag_approval():
    index = InMemoryKeywordIndex()
    allowed = _chunk("長者高血壓照護可注意規律量血壓、均衡飲食與活動。")
    license_review = _chunk(
        "高血壓文章但授權未確認，期末非商用展示仍可保留 citation 使用。",
        source_id="health99",
        chunk_id="doc-2#chunk-1",
        copyright_status=CopyrightStatus.NEEDS_REVIEW,
    )
    blocked = _chunk("未核准來源。", chunk_id="doc-3#chunk-1", approved_for_rag=False)
    index.add(allowed)
    index.add(license_review)
    index.add(blocked)

    results = HealthEducationRetriever(index).retrieve("阿公血壓高要注意什麼？")

    assert [result.chunk.metadata.chunk_id for result in results] == [
        "doc-1#chunk-1",
        "doc-2#chunk-1",
    ]


def test_retriever_normalizes_mixed_taiwanese_sleep_query():
    index = InMemoryKeywordIndex()
    index.add(_chunk("長者睡眠可先維持規律作息，白天適度活動。", topic="睡眠"))

    results = HealthEducationRetriever(index).retrieve("阿嬤最近袂睏，白天沒精神")

    assert len(results) == 1
    assert results[0].chunk.metadata.topic == "睡眠"


def test_retriever_excludes_discovery_sources_from_answer_evidence():
    index = InMemoryKeywordIndex()
    index.add(_chunk("高血壓新聞。", source_role=SourceRole.DISCOVERY))

    assert HealthEducationRetriever(index).retrieve("高血壓") == ()


@pytest.mark.parametrize(
    "query",
    [
        "明天台北會不會下雨？",
        "台積電股票明天會漲嗎？",
        "紅燒牛肉怎麼煮最好吃？",
        "請用十年前的衛教告訴我最新疫苗接種規定",
        "衛福部今天發布了哪些最新新聞？",
    ],
)
def test_retriever_rejects_obvious_non_answer_intents_before_search(query: str):
    class UnexpectedStore:
        def search(self, vector, *, top_k):
            raise AssertionError("不應執行向量檢索")

        def keyword_search(self, normalized_query, *, top_k):
            raise AssertionError("不應執行 keyword 檢索")

    from kinsun.rag.embeddings import CharacterHashEmbedding

    retriever = HealthEducationRetriever(
        vector_store=UnexpectedStore(),
        embedding_model=CharacterHashEmbedding(dimensions=8),
    )

    assert retriever.retrieve(query) == ()


def test_retriever_does_not_reject_weather_context_in_health_question():
    index = _index_with(_chunk("天氣冷時，高血壓長者仍應規律量血壓。"))

    results = HealthEducationRetriever(index).retrieve("天氣冷時高血壓要注意什麼？")

    assert results


def test_keyword_terms_remove_complete_question_fillers():
    terms = extract_keyword_terms("高血壓平常要注意什麼？")

    assert terms[0] == "高血壓"


def test_vector_failure_falls_back_to_database_keyword_search():
    expected = HealthEducationRetriever(_index_with(_chunk("高血壓照護包含規律量血壓。"))).retrieve(
        "高血壓"
    )[0]

    class BrokenVectorStore:
        def search(self, vector, *, top_k):
            raise RuntimeError("vector down")

        def keyword_search(self, query, *, top_k):
            return (expected,)

    from kinsun.rag.embeddings import CharacterHashEmbedding

    retriever = HealthEducationRetriever(
        vector_store=BrokenVectorStore(),
        embedding_model=CharacterHashEmbedding(dimensions=8),
    )

    results = retriever.retrieve("高血壓平常要注意什麼？")

    assert results[0].retrieval_method == "keyword"


def test_both_retrieval_paths_failing_returns_empty_evidence():
    class BrokenStore:
        def search(self, vector, *, top_k):
            raise RuntimeError("vector down")

        def keyword_search(self, query, *, top_k):
            raise RuntimeError("keyword down")

    from kinsun.rag.embeddings import CharacterHashEmbedding

    retriever = HealthEducationRetriever(
        vector_store=BrokenStore(),
        embedding_model=CharacterHashEmbedding(dimensions=8),
    )

    assert retriever.retrieve("高血壓平常要注意什麼？") == ()


def test_answer_policy_builds_grounded_answer_with_citation():
    evidence = (
        HealthEducationRetriever(_index_with(_chunk("高血壓照護包含規律量血壓。"))).retrieve(
            "高血壓"
        )[0],
    )

    answer = AnswerPolicy().build_answer("高血壓要注意什麼？", evidence)

    assert answer.safety_level == SafetyLevel.NORMAL
    assert answer.requires_safety_attention is False
    assert answer.citations[0].source_id == "hpa_health_education"
    assert "規律量血壓" in answer.answer


def test_answer_policy_refuses_when_evidence_is_empty():
    answer = AnswerPolicy().build_answer("沒來源的偏方可不可以治糖尿病？", ())

    assert answer.safety_level == SafetyLevel.UNSUPPORTED
    assert answer.citations == ()
    assert answer.requires_safety_attention is False


@pytest.mark.parametrize(
    "query",
    [
        "我是不是中風？",
        "血壓藥可以停藥嗎？",
        "藥量可不可以加倍？",
        "我要不要去急診？",
    ],
)
def test_answer_policy_blocks_diagnosis_and_medication_requests(query: str):
    answer = AnswerPolicy().build_answer(query, ())

    assert answer.safety_level == SafetyLevel.UNSUPPORTED
    assert answer.requires_safety_attention is True


def test_answer_policy_escalates_red_flag_signals_without_using_rag():
    evidence = HealthEducationRetriever(_index_with(_chunk("胸痛衛教文字。"))).retrieve("胸痛")

    answer = AnswerPolicy().build_answer("胸口很痛又喘不過氣", evidence, has_risk_signal=True)

    assert answer.safety_level == SafetyLevel.URGENT
    assert answer.requires_safety_attention is True
    assert answer.citations == ()


def _index_with(chunk: DocumentChunk) -> InMemoryKeywordIndex:
    index = InMemoryKeywordIndex()
    index.add(chunk)
    return index
