"""Interfaces (ports) between the app and its replaceable parts.

Ingestion and the answer flow depend on these, never on each other and never on a concrete
database or vendor. Real adapters (Pinecone, OpenAI, a cross-encoder) can be added later
without touching either side.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import NamedTuple, Protocol, runtime_checkable

from citedesk.domain.models import (
    Chunk,
    Document,
    DocumentStatus,
    ModelHealth,
    ModelInfo,
    Passage,
    UsageSnapshot,
)


class Embedder(Protocol):
    dimension: int  # numbers per vector; a vector database index must be created with this size

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed passages for indexing."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a question. Some models use a different prompt for questions than for passages."""
        ...


class IndexItem(NamedTuple):
    chunk_id: str
    document_id: str
    vector: list[float]


class VectorIndex(Protocol):
    """Holds vectors of *published* chunks only."""

    def upsert(self, items: Sequence[IndexItem]) -> None: ...

    def delete_document(self, document_id: str) -> None: ...

    def ids(self) -> set[str]:
        """Every chunk id currently stored."""
        ...

    def delete_ids(self, chunk_ids: Sequence[str]) -> None: ...

    def search(self, vector: Sequence[float], limit: int) -> list[tuple[str, float]]:
        """Return (chunk_id, similarity), best first."""
        ...


class Reranker(Protocol):
    def rerank(self, question: str, passages: Sequence[Passage]) -> list[Passage]:
        """Return the passages best-first, with `score` set to a relevance (higher is better).

        The scale depends on the reranker, so the relevance threshold is set per backend.
        """
        ...


class AnswerWriter(Protocol):
    def write(self, question: str, passages: Sequence[Passage], *, strict: bool) -> str:
        """Draft an answer whose sentences end with [n] markers (n counts from 1).

        `strict=True` asks for a more conservative draft (quotes only) and is used on retry.
        """
        ...


@runtime_checkable
class ModelStatus(Protocol):
    """Implemented by writers that can describe themselves and report whether they work."""

    def info(self) -> ModelInfo: ...

    def check(self) -> ModelHealth:
        """Make a small real request (if the writer uses a remote model) and report the result."""
        ...

    def usage(self) -> UsageSnapshot | None:
        """Calls and tokens used since the process started, or None if not tracked."""
        ...


class DocumentRepository(Protocol):
    """Write side, used by ingestion."""

    def add_document(self, document: Document, chunks: Sequence[Chunk], *, actor: str) -> None: ...

    def get_document(self, document_id: str) -> Document | None: ...

    def find_by_hash(self, content_hash: str) -> Document | None: ...

    def get_chunks(self, document_id: str) -> list[Chunk]: ...

    def list_documents(self) -> list[Document]: ...

    def update_license(
        self, document_id: str, *, license: str, terms_url: str | None, actor: str, when: datetime
    ) -> None:
        """Record the license and terms of a document, with an audit entry. Search is unaffected."""
        ...

    def transition(
        self, document_id: str, status: DocumentStatus, *, actor: str, when: datetime
    ) -> None:
        """Change status, bump the corpus version and write an audit entry, atomically."""
        ...

    def replace_published(self, old_id: str, new_id: str, *, actor: str, when: datetime) -> None:
        """Retire a published document and publish its replacement in one transaction.

        The corpus version goes up once, so no question ever sees both versions or neither.
        """
        ...


class CorpusReader(Protocol):
    """Read side, used by the answer flow. Only published content is visible."""

    def corpus_version(self) -> int: ...

    def published_passages(self) -> list[Passage]: ...

    def get_passage(self, chunk_id: str) -> Passage | None: ...
