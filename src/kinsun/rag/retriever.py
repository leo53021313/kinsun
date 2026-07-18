"""衛教 RAG 檢索器。"""

from __future__ import annotations

import logging
import re

from kinsun.rag.embeddings import QueryEmbeddingModel
from kinsun.rag.keyword_index import InMemoryKeywordIndex
from kinsun.rag.reranker import rerank
from kinsun.rag.schemas import SearchResult, SourceRole

logger = logging.getLogger("kinsun.rag.retriever")

_KEYWORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")

_SYNONYMS = {
    "血壓高": "高血壓",
    "三高": "高血壓 高血糖 高血脂",
    "老人": "長者",
    "阿公": "長者",
    "阿嬤": "長者",
    "睡不著": "睡眠",
    "袂睏": "睡眠",
    "睏袂去": "睡眠",
}

_QUESTION_FILLERS = (
    "平常要",
    "平常",
    "可以",
    "應該",
    "最近",
    "請問",
    "怎麼辦",
    "注意什麼",
    "什麼",
    "長輩",
    "阿公",
    "阿嬤",
)

_FORECAST_TERMS = ("天氣", "氣溫", "下雨", "降雨", "颱風", "氣象")
_FORECAST_INTENT_TERMS = ("今天", "明天", "後天", "會不會", "幾度", "預報")
_FINANCE_TERMS = ("股票", "股價", "台積電", "漲停", "跌停", "會漲", "會跌")
_COOKING_TERMS = ("食譜", "怎麼煮", "如何煮", "紅燒", "清蒸", "料理作法")
_STALE_REQUEST_TERMS = ("十年前", "過期衛教", "舊版衛教", "已廢止")
_DISCOVERY_REQUEST_TERMS = ("新聞", "今天發布", "最新公告", "發布了哪些")


class HealthEducationRetriever:
    def __init__(
        self,
        keyword_index: InMemoryKeywordIndex | None = None,
        *,
        vector_store=None,
        embedding_model: QueryEmbeddingModel | None = None,
    ) -> None:
        self._keyword_index = keyword_index
        self._vector_store = vector_store
        self._embedding_model = embedding_model

    def retrieve(self, query: str, *, top_k: int = 5) -> tuple[SearchResult, ...]:
        normalized = normalize_query(query)
        if _is_obviously_out_of_scope(normalized):
            return ()
        results: list[SearchResult] = []
        if self._can_use_vector_search():
            try:
                query_vector = self._embedding_model.embed_query(normalized)
                results.extend(self._vector_store.search(query_vector, top_k=top_k * 3))
            except Exception:  # noqa: BLE001 - 向量路徑故障時退化為 keyword
                logger.exception("RAG 向量檢索失敗，改走 keyword")
        if self._keyword_index is not None:
            try:
                results.extend(self._keyword_index.search(normalized, top_k=top_k * 3))
            except Exception:  # noqa: BLE001 - 兩路皆失敗時安全回空 evidence
                logger.exception("RAG 記憶體 keyword 檢索失敗")
        elif self._vector_store is not None:
            try:
                results.extend(self._vector_store.keyword_search(normalized, top_k=top_k * 3))
            except Exception:  # noqa: BLE001 - 兩路皆失敗時安全回空 evidence
                logger.exception("RAG keyword 檢索失敗")
        filtered = tuple(result for result in results if _is_allowed_chunk(result))
        ranked = rerank(filtered, top_k=top_k * 3)
        threshold = self._relevance_threshold()
        if threshold is not None:
            ranked = tuple(result for result in ranked if result.score >= threshold)
        return ranked[:top_k]

    def _can_use_vector_search(self) -> bool:
        if self._vector_store is None or self._embedding_model is None:
            return False
        configuration_reader = getattr(self._vector_store, "active_embedding_configuration", None)
        if configuration_reader is None:
            return True
        try:
            configuration = configuration_reader()
        except Exception:  # noqa: BLE001 - 設定查詢失敗仍可走 keyword
            logger.exception("RAG 無法讀取 active release 的 embedding 設定")
            return False
        expected = (self._embedding_model.model_name, self._embedding_model.dimensions)
        if configuration != expected:
            logger.warning(
                "RAG embedding 設定不一致，停用向量路徑：active=%s runtime=%s",
                configuration,
                expected,
            )
            return False
        return True

    def active_release_version(self) -> str:
        if self._vector_store is None:
            return ""
        reader = getattr(self._vector_store, "active_release_version", None)
        if reader is None:
            return ""
        try:
            return str(reader() or "")
        except Exception:  # noqa: BLE001 - 版本觀測失敗不影響回答
            logger.exception("RAG 無法讀取 active release 版本")
            return ""

    def _relevance_threshold(self) -> float | None:
        if self._vector_store is None:
            return None
        reader = getattr(self._vector_store, "active_relevance_threshold", None)
        if reader is None:
            return None
        try:
            return reader()
        except Exception:  # noqa: BLE001 - threshold 觀測失敗時不阻斷 keyword 降級
            logger.exception("RAG 無法讀取 relevance threshold")
            return float("inf")


def normalize_query(query: str) -> str:
    normalized = query.strip()
    for source, target in _SYNONYMS.items():
        normalized = normalized.replace(source, f"{source} {target}")
    return normalized


def _is_obviously_out_of_scope(query: str) -> bool:
    """只擋明確不屬於 ANSWER 衛教索引的意圖，避免用 threshold 猜語意。"""
    compact = re.sub(r"\s+", "", query.lower())
    has_forecast_intent = any(term in compact for term in _FORECAST_INTENT_TERMS)
    asks_forecast = has_forecast_intent and any(term in compact for term in _FORECAST_TERMS)
    return asks_forecast or any(
        term in compact
        for term in (
            *_FINANCE_TERMS,
            *_COOKING_TERMS,
            *_STALE_REQUEST_TERMS,
            *_DISCOVERY_REQUEST_TERMS,
        )
    )


def extract_keyword_terms(query: str) -> tuple[str, ...]:
    normalized = normalize_query(query).lower()
    terms: list[str] = []
    seen: set[str] = set()
    for match in _KEYWORD_RE.finditer(normalized):
        raw = match.group(0)
        if raw.isascii():
            _append_term(raw, terms, seen)
            continue
        compact = raw
        for filler in _QUESTION_FILLERS:
            compact = compact.replace(filler, "")
        if len(compact) <= 6:
            _append_term(compact, terms, seen)
        for size in (4, 3, 2):
            if len(terms) >= 24:
                break
            for start in range(0, len(compact) - size + 1):
                _append_term(compact[start : start + size], terms, seen)
                if len(terms) >= 24:
                    break
    return tuple(terms[:24])


def _append_term(term: str, terms: list[str], seen: set[str]) -> None:
    if len(term) < 2 or term in seen:
        return
    seen.add(term)
    terms.append(term)


def _is_allowed_chunk(result: SearchResult) -> bool:
    metadata = result.chunk.metadata
    return metadata.approved_for_rag and metadata.source_role == SourceRole.ANSWER
