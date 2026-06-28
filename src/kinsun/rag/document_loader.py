"""文件載入介面與測試用實作。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kinsun.rag.schemas import ChunkMetadata


@dataclass(frozen=True)
class LoadedDocument:
    text: str
    metadata: ChunkMetadata


class DocumentLoader(Protocol):
    def load(self, document_id: str) -> LoadedDocument: ...


class StaticDocumentLoader:
    def __init__(self, documents: dict[str, LoadedDocument]) -> None:
        self._documents = documents

    def load(self, document_id: str) -> LoadedDocument:
        return self._documents[document_id]
