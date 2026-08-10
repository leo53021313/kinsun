"""衛教 RAG ingestion pipeline：文件 → chunk → embedding → vector store。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from kinsun.rag.chunker import chunk_text
from kinsun.rag.content_filter import judge_admission
from kinsun.rag.crawler import ParsedPage
from kinsun.rag.embeddings import QueryEmbeddingModel
from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CrawlStatus,
    Language,
    MedicalScope,
    RagDocument,
    Source,
    SourceRole,
)
from kinsun.rag.text_cleaner import clean_text, strip_page_furniture

_TOPIC_HINTS = {
    "高血壓": ("高血壓", "血壓", "三高"),
    "糖尿病": ("糖尿病", "血糖"),
    "高血脂": ("高血脂", "血脂", "膽固醇"),
    "睡眠": ("睡眠", "失眠", "睡不著", "袂睏"),
    "運動": ("運動", "活動", "肌力"),
    "飲食": ("飲食", "營養", "蔬果", "鹽"),
    "疫苗": ("疫苗", "接種"),
    "用藥安全": ("用藥", "藥物", "藥品"),
    "預防保健": ("預防", "篩檢", "健康檢查"),
}


class RagWriteStore(Protocol):
    def upsert_source(self, source: Source) -> None: ...
    def upsert_document(self, document: RagDocument) -> None: ...
    def add(self, chunk, vector: tuple[float, ...]) -> None: ...
    def save_document(
        self,
        document: RagDocument,
        prepared_chunks: tuple[tuple[object, tuple[float, ...]], ...],
        *,
        index_version: str | None,
        embedding_model_name: str,
        embedding_dimensions: int,
        fetched_at: float,
        parser_used: str,
        operator_or_job_id: str,
    ) -> None: ...
    def save_discovery_document(
        self,
        document: RagDocument,
        *,
        index_version: str,
        fetched_at: float,
        operator_or_job_id: str,
    ) -> None: ...
    def log_ingestion(
        self,
        *,
        source_id: str,
        fetched_at: float,
        content_hash: str,
        chunk_count: int,
        parser_used: str,
        status: str,
        error_message: str | None,
        operator_or_job_id: str,
    ) -> None: ...


@dataclass(frozen=True)
class SeedDocument:
    source_id: str
    url: str
    title: str
    publisher: str
    text: str
    topic: str = "一般衛教"
    language: Language = Language.ZH_TW
    audience: Audience = Audience.GENERAL_PUBLIC
    medical_scope: MedicalScope = MedicalScope.HEALTH_EDUCATION
    published_at: date | None = None
    updated_at: date | None = None


class IngestionPipeline:
    def __init__(
        self,
        *,
        store: RagWriteStore,
        embedding_model: QueryEmbeddingModel,
        max_chunk_chars: int = 700,
        clock=lambda: datetime.now(),
    ) -> None:
        if not 80 <= max_chunk_chars <= 700:
            raise ValueError("max_chunk_chars 必須介於 80 到 700。")
        self._store = store
        self._embedding_model = embedding_model
        self._max_chunk_chars = max_chunk_chars
        self._clock = clock
        # 本輪已收錄的 canonical URL → 收錄它的 source_id。
        # deduplicate_documents 只看得到單一來源的批次；同一個網站被切成多個來源
        # （如 HPA 五個），爬深拉高後都會逛到共用的首頁與導覽頁，同一個 URL 被收
        # 好幾次——2026-07-29 實測 1,297 份文件只有 597 個不重複 URL、release 的
        # chunk 有 47% 是重複頁面，白燒嵌入配額且結構閘門直接擋下。
        # 一個 pipeline 實例＝一輪 ingest，故此狀態的生命週期正好是一輪。
        self._claimed_urls: dict[str, str] = {}
        # 本輪已收錄的 content_hash → 收錄它的 source_id。
        # 只比 URL 擋不住「不同網址、同一份內容」：衛福部的 np-16-1.html 與
        # lp-16-1.html 都渲染〈焦點新聞〉，2026-08-05 實測三組跨來源重複內容
        # 讓結構閘門以「有重複內容 hash」擋下整個 release。
        self._claimed_hashes: dict[str, str] = {}

    def ingest_seed_documents(
        self,
        source: Source,
        documents: tuple[SeedDocument, ...],
        *,
        operator_or_job_id: str,
        index_version: str | None = None,
    ) -> tuple[RagDocument, ...]:
        rag_documents = tuple(
            _seed_to_document(source, doc, self._clock().date()) for doc in documents
        )
        self.ingest_documents(
            source,
            rag_documents,
            operator_or_job_id=operator_or_job_id,
            index_version=index_version,
        )
        return rag_documents

    def ingest_pages(
        self,
        source: Source,
        pages: tuple[ParsedPage, ...],
        *,
        operator_or_job_id: str,
        index_version: str | None = None,
    ) -> tuple[RagDocument, ...]:
        pages = _strip_site_chrome(pages)
        documents = tuple(_page_to_document(source, page, self._clock().date()) for page in pages)
        # 收錄判定只作用在爬取結果：seed 檔是人工整理過的，不需要也不該被過濾。
        admitted: list[RagDocument] = []
        for document in documents:
            verdict = judge_admission(title=document.title, content=document.text)
            if verdict.is_admitted:
                admitted.append(document)
                continue
            self._store.log_ingestion(
                source_id=source.source_id,
                document_id=document.document_id,
                url=document.url,
                fetched_at=self._clock().timestamp(),
                content_hash=document.content_hash,
                chunk_count=0,
                parser_used="content_filter",
                status=CrawlStatus.SKIPPED.value,
                error_message=f"未收錄：{verdict.reason}",
                operator_or_job_id=operator_or_job_id,
            )
        self.ingest_documents(
            source,
            tuple(admitted),
            operator_or_job_id=operator_or_job_id,
            index_version=index_version,
        )
        return tuple(admitted)

    def _claim_urls(
        self,
        documents: tuple[RagDocument, ...],
        source: Source,
    ) -> tuple[tuple[RagDocument, ...], tuple[tuple[RagDocument, str], ...]]:
        """本輪內同一個 canonical URL 或同一份內容只讓第一個來源收錄。

        先到先得——呼叫端負責讓 ANSWER 來源排在 DISCOVERY 之前（見
        `source_registry.order_answer_first`），否則衛教內文可能被只留 membership
        的 discovery 來源搶走、不建回答向量。

        兩把鑰匙都要：`deduplicate_documents` 的 hash 那一關只看得到單一來源的
        批次，跨來源的同內容不同網址（衛福部 np-16-1.html 與 lp-16-1.html 都是
        〈焦點新聞〉）只有在這裡才擋得住。
        """
        kept: list[RagDocument] = []
        discarded: list[tuple[RagDocument, str]] = []
        for document in documents:
            canonical = normalize_url(document.url)
            url_owner = self._claimed_urls.get(canonical)
            if url_owner is not None:
                discarded.append((document, f"本輪已由來源 {url_owner} 收錄同一個 URL。"))
                continue
            hash_owner = self._claimed_hashes.get(document.content_hash)
            if hash_owner is not None:
                discarded.append((document, f"本輪已由來源 {hash_owner} 收錄同一份內容。"))
                continue
            self._claimed_urls[canonical] = source.source_id
            self._claimed_hashes[document.content_hash] = source.source_id
            kept.append(document)
        return tuple(kept), tuple(discarded)

    def ingest_documents(
        self,
        source: Source,
        documents: tuple[RagDocument, ...],
        *,
        operator_or_job_id: str,
        index_version: str | None = None,
    ) -> None:
        self._store.upsert_source(source)
        normalized_documents = tuple(_normalize_document(document) for document in documents)
        kept_documents, discarded = deduplicate_documents(normalized_documents)
        kept_documents, cross_source_discarded = self._claim_urls(kept_documents, source)
        discarded = discarded + cross_source_discarded
        for document, reason in discarded:
            self._store.log_ingestion(
                source_id=source.source_id,
                document_id=document.document_id,
                url=document.url,
                fetched_at=self._clock().timestamp(),
                content_hash=document.content_hash,
                chunk_count=0,
                parser_used="deduplication",
                status=CrawlStatus.SKIPPED.value,
                error_message=reason,
                operator_or_job_id=operator_or_job_id,
            )
        for document in kept_documents:
            try:
                if index_version and source.role == SourceRole.DISCOVERY:
                    self._store.save_discovery_document(
                        document,
                        index_version=index_version,
                        fetched_at=self._clock().timestamp(),
                        operator_or_job_id=operator_or_job_id,
                    )
                    continue
                reuse_document = getattr(self._store, "reuse_document", None)
                if (
                    index_version
                    and reuse_document is not None
                    and reuse_document(
                        document,
                        source_role=source.role,
                        index_version=index_version,
                        fetched_at=self._clock().timestamp(),
                        operator_or_job_id=operator_or_job_id,
                    )
                ):
                    continue
                chunks = chunk_text(
                    document.text,
                    _metadata_for(document, source),
                    max_chars=self._max_chunk_chars,
                )
                if not chunks:
                    raise ValueError("文件清理後沒有可入庫文字。")
                batch_embed = getattr(self._embedding_model, "embed_documents", None)
                if callable(batch_embed):
                    vectors = batch_embed(
                        tuple(chunk.text for chunk in chunks),
                        title=document.title,
                    )
                else:
                    vectors = tuple(
                        self._embedding_model.embed_document(
                            chunk.text,
                            title=chunk.metadata.title,
                        )
                        for chunk in chunks
                    )
                if len(vectors) != len(chunks):
                    raise ValueError("embedding 數量與 chunks 不一致。")
                prepared_chunks = []
                for chunk, vector in zip(chunks, vectors, strict=True):
                    if not vector:
                        raise ValueError("embedding 不可為空。")
                    prepared_chunks.append((chunk, vector))
                self._store.save_document(
                    document,
                    tuple(prepared_chunks),
                    index_version=index_version,
                    embedding_model_name=self._embedding_model.model_name,
                    embedding_dimensions=self._embedding_model.dimensions,
                    fetched_at=self._clock().timestamp(),
                    parser_used="ingestion",
                    operator_or_job_id=operator_or_job_id,
                )
            except Exception as exc:  # noqa: BLE001 - 單篇失敗不中斷整批（✅ 庚-39 冗餘 union 收斂）
                self._store.log_ingestion(
                    source_id=source.source_id,
                    document_id=document.document_id,
                    url=document.url,
                    fetched_at=self._clock().timestamp(),
                    content_hash=document.content_hash,
                    chunk_count=0,
                    parser_used="ingestion",
                    status=CrawlStatus.FAILED.value,
                    error_message=str(exc),
                    operator_or_job_id=operator_or_job_id,
                )


def load_seed_documents(path: Path) -> tuple[SeedDocument, ...]:
    documents: list[SeedDocument] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            item = json.loads(line)
            documents.append(
                SeedDocument(
                    source_id=item["source_id"],
                    url=item["url"],
                    title=item["title"],
                    publisher=item["publisher"],
                    text=item["text"],
                    topic=item.get("topic", "一般衛教"),
                    language=Language(item.get("language", Language.ZH_TW.value)),
                    audience=Audience(item.get("audience", Audience.GENERAL_PUBLIC.value)),
                    medical_scope=MedicalScope(
                        item.get("medical_scope", MedicalScope.HEALTH_EDUCATION.value)
                    ),
                    published_at=_parse_date(item.get("published_at")),
                    updated_at=_parse_date(item.get("updated_at")),
                )
            )
    return tuple(documents)


def group_seed_documents_by_source(
    documents: tuple[SeedDocument, ...],
) -> dict[str, tuple[SeedDocument, ...]]:
    grouped: dict[str, list[SeedDocument]] = {}
    for document in documents:
        grouped.setdefault(document.source_id, []).append(document)
    return {source_id: tuple(rows) for source_id, rows in grouped.items()}


def _seed_to_document(source: Source, seed: SeedDocument, retrieved_at: date) -> RagDocument:
    cleaned = clean_text(seed.text)
    content_hash = _hash(cleaned)
    document_id = _document_id(source.source_id, seed.url, content_hash)
    return RagDocument(
        document_id=document_id,
        source_id=source.source_id,
        url=normalize_url(seed.url),
        title=seed.title,
        publisher=seed.publisher or source.publisher,
        text=cleaned,
        content_hash=content_hash,
        source_type=source.source_type,
        language=seed.language,
        topic=seed.topic,
        audience=seed.audience,
        medical_scope=seed.medical_scope,
        trust_level=source.trust_level,
        copyright_status=source.copyright_status,
        published_at=seed.published_at,
        updated_at=seed.updated_at,
        retrieved_at=retrieved_at,
    )


# 跨文件骨架偵測：同來源多數頁面都出現的行視為站台骨架。低於這個頁數不做比對，
# 樣本太小時「兩篇剛好都提到同一句」不足以判定為骨架。
_CHROME_MIN_PAGES = 5
_CHROME_PAGE_RATIO = 0.5


def _strip_site_chrome(pages: tuple[ParsedPage, ...]) -> tuple[ParsedPage, ...]:
    """剝掉整批頁面共有的站台骨架（選單、頁尾、客服電話）。

    `strip_page_furniture` 的規則是照 hpa 的版型寫的；cdc.gov.tw 沒有「首頁 >」
    麵包屑也沒有「跳到主要內容區塊」，那些規則一條都對不上，整份站台選單會原封
    不動進索引（2026-08-01 實測：cdc_advocacy 的 17 篇全是選單，產生 38 個純導覽
    chunk）。與其為每個網站寫一套規則，不如用「跨文件重複」這個站台無關的訊號。

    刻意不用「行很短」或「沒有句號」判定——衛教海報整篇都是條列，〈高血壓〉這種
    海報還是 golden set 的正解，用形狀判定會把它們一起殺掉。海報的每一行只出現在
    自己那一篇，不會出現在多數頁面裡。
    """
    if len(pages) < _CHROME_MIN_PAGES:
        return pages
    appearances: dict[str, int] = {}
    for page in pages:
        for line in {raw.strip() for raw in page.text.splitlines() if raw.strip()}:
            appearances[line] = appearances.get(line, 0) + 1
    threshold = len(pages) * _CHROME_PAGE_RATIO
    chrome = {line for line, count in appearances.items() if count > threshold}
    if not chrome:
        return pages
    return tuple(
        replace(
            page,
            text="\n".join(
                line
                for raw in page.text.splitlines()
                if (line := raw.strip()) and line not in chrome
            ),
        )
        for page in pages
    )


def _page_to_document(source: Source, page: ParsedPage, retrieved_at: date) -> RagDocument:
    title = _strip_publisher_prefix(page.title, source.publisher)
    # 先剝網頁樣板再清理：政府網站的選單是普通 div，HTML 解析器的 nav／footer
    # 規則攔不到，只能在文字層處理（見 text_cleaner.strip_page_furniture）。
    cleaned = clean_text(strip_page_furniture(clean_text(page.text), title=title))
    content_hash = _hash(cleaned)
    document_id = _document_id(source.source_id, page.url, content_hash)
    return RagDocument(
        document_id=document_id,
        source_id=source.source_id,
        url=normalize_url(page.url),
        title=title or source.title,
        publisher=source.publisher,
        text=cleaned,
        content_hash=content_hash,
        source_type=source.source_type,
        language=Language.ZH_TW if _looks_zh_tw(cleaned) else Language.EN,
        topic=_infer_topic(f"{title}\n{cleaned}"),
        audience=Audience.GENERAL_PUBLIC,
        medical_scope=MedicalScope.HEALTH_EDUCATION,
        trust_level=source.trust_level,
        copyright_status=source.copyright_status,
        published_at=page.published_at,
        updated_at=page.published_at,
        retrieved_at=retrieved_at,
    )


_PUBLISHER_PREFIX_SEPARATORS = ("-", "－", "|", "｜", "–", "—")


def _strip_publisher_prefix(title: str, publisher: str) -> str:
    """去掉網頁 <title> 常見的「機關名 - 」前綴。

    留著前綴會讓「內文只是標題複讀」的判定失效：內文寫的是裸標題，比對對象卻
    帶著機關名，兩者永遠對不上（2026-08-01 對真實網站煙霧測試時發現，
    附件索引頁因此矇混過關）。
    """
    stripped = title.strip()
    if not publisher or not stripped.startswith(publisher):
        return stripped
    remainder = stripped[len(publisher) :].lstrip()
    for separator in _PUBLISHER_PREFIX_SEPARATORS:
        if remainder.startswith(separator):
            return remainder[len(separator) :].strip()
    return stripped


def _metadata_for(document: RagDocument, source: Source) -> ChunkMetadata:
    return ChunkMetadata(
        source_id=document.source_id,
        document_id=document.document_id,
        chunk_id=f"{document.document_id}#chunk-0",
        title=document.title,
        publisher=document.publisher,
        source_url=document.url,
        source_type=document.source_type,
        language=document.language,
        topic=document.topic,
        audience=document.audience,
        medical_scope=document.medical_scope,
        trust_level=document.trust_level,
        approved_for_rag=source.approved_for_rag,
        copyright_status=document.copyright_status,
        source_published_at=document.published_at,
        source_updated_at=document.updated_at,
        retrieved_at=document.retrieved_at,
        last_reviewed_at=document.retrieved_at,
        source_role=source.role,
    )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _document_id(source_id: str, url: str, content_hash: str) -> str:
    del url
    return f"{source_id}:{content_hash[:24]}"


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, host, path, parsed.query, ""))


def deduplicate_documents(
    documents: tuple[RagDocument, ...],
) -> tuple[tuple[RagDocument, ...], tuple[tuple[RagDocument, str], ...]]:
    """同 URL 留最新；同內容留 HTTPS 且 canonical URL 較短者。"""
    by_url: dict[str, RagDocument] = {}
    discarded: list[tuple[RagDocument, str]] = []
    for document in documents:
        canonical = normalize_url(document.url)
        normalized = document if document.url == canonical else _replace_url(document, canonical)
        previous = by_url.get(canonical)
        if previous is None:
            by_url[canonical] = normalized
            continue
        if _document_recency(normalized) >= _document_recency(previous):
            discarded.append((previous, "同一 canonical URL 已有較新文件。"))
            by_url[canonical] = normalized
        else:
            discarded.append((normalized, "同一 canonical URL 已有較新文件。"))

    by_hash: dict[str, RagDocument] = {}
    for document in by_url.values():
        previous = by_hash.get(document.content_hash)
        if previous is None:
            by_hash[document.content_hash] = document
            continue
        preferred = min((previous, document), key=_canonical_preference)
        dropped = document if preferred is previous else previous
        by_hash[document.content_hash] = preferred
        discarded.append((dropped, "相同內容 hash 已保留較佳 canonical URL。"))
    return tuple(by_hash.values()), tuple(discarded)


def _replace_url(document: RagDocument, url: str) -> RagDocument:
    return replace(document, url=url)


def _normalize_document(document: RagDocument) -> RagDocument:
    cleaned = clean_text(document.text)
    content_hash = _hash(cleaned)
    return replace(
        document,
        document_id=_document_id(document.source_id, document.url, content_hash),
        text=cleaned,
        content_hash=content_hash,
        url=normalize_url(document.url),
    )


def _document_recency(document: RagDocument) -> tuple[date, date, str, str]:
    """同時間戳以穩定欄位決勝，避免資料庫列順序造成 release 漂移。"""
    return (
        document.updated_at or document.published_at or date.min,
        document.retrieved_at,
        document.content_hash,
        document.source_id,
    )


def _canonical_preference(document: RagDocument) -> tuple[int, int, str]:
    return (0 if document.url.startswith("https://") else 1, len(document.url), document.url)


def _infer_topic(text: str) -> str:
    for topic, hints in _TOPIC_HINTS.items():
        if any(hint in text for hint in hints):
            return topic
    return "一般衛教"


def _looks_zh_tw(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text[:1000])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)
