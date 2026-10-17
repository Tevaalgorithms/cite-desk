"""The admin workflow: add a document, preview it, publish it, take it down.

Nothing is searchable until `publish` succeeds. This module knows nothing about how
questions are answered.
"""

import hashlib
import uuid
from datetime import UTC, datetime

from citedesk.domain.models import Chunk, Document, DocumentStatus, searchable_text
from citedesk.domain.ports import DocumentRepository, Embedder, IndexItem, VectorIndex
from citedesk.ingestion.chunking import chunk_document
from citedesk.ingestion.fetching import UrlFetcher
from citedesk.ingestion.parsing import ContentType, parse


class DuplicateDocumentError(ValueError):
    def __init__(self, existing: Document) -> None:
        super().__init__(f"Same content already added as document {existing.id}")
        self.existing = existing


class PublishBlockedError(ValueError):
    """The document may not be published yet, for example because its license is unknown."""


class DocumentNotFoundError(KeyError):
    pass


class IngestionService:
    def __init__(
        self,
        repository: DocumentRepository,
        embedder: Embedder,
        index: VectorIndex,
        fetcher: UrlFetcher | None = None,
        *,
        chunk_max_chars: int = 1200,
        min_document_chars: int = 100,
    ) -> None:
        self._repository = repository
        self._embedder = embedder
        self._index = index
        self._fetcher = fetcher
        self._chunk_max_chars = chunk_max_chars
        self._min_document_chars = min_document_chars

    def add_text(
        self,
        content: str,
        *,
        content_type: ContentType,
        title: str,
        source_name: str,
        actor: str,
        license: str | None = None,
        terms_url: str | None = None,
        source_url: str | None = None,
    ) -> Document:
        """Parse, chunk and store content as a draft. It is not searchable yet."""
        parsed = parse(
            content, content_type, fallback_title=title, min_chars=self._min_document_chars
        )
        content_hash = hashlib.sha256(" ".join(content.split()).encode()).hexdigest()
        existing = self._repository.find_by_hash(content_hash)
        if existing is not None:
            raise DuplicateDocumentError(existing)

        document = Document(
            id=uuid.uuid4().hex[:12],
            title=parsed.title,
            source_name=source_name,
            source_url=source_url,
            license=license,
            terms_url=terms_url,
            content_hash=content_hash,
            created_at=datetime.now(UTC),
        )
        drafts = chunk_document(parsed, max_chars=self._chunk_max_chars)
        chunks = [
            Chunk(
                id=f"{document.id}:{ordinal:04d}",
                document_id=document.id,
                ordinal=ordinal,
                section_path=draft.section_path,
                text=draft.text,
            )
            for ordinal, draft in enumerate(drafts)
        ]
        self._repository.add_document(document, chunks, actor=actor)
        return document

    def add_url(
        self,
        url: str,
        *,
        source_name: str,
        actor: str,
        license: str | None = None,
        terms_url: str | None = None,
    ) -> Document:
        """Fetch a web page safely, then add it like any other text."""
        if self._fetcher is None:
            raise RuntimeError("URL import is not configured")
        page = self._fetcher.fetch(url)
        return self.add_text(
            page.text,
            content_type=page.content_type,
            title=url,
            source_name=source_name,
            actor=actor,
            license=license,
            terms_url=terms_url,
            source_url=page.url,
        )

    def preview(self, document_id: str) -> list[Chunk]:
        """The chunks an admin reviews before publishing."""
        self._require(document_id)
        return self._repository.get_chunks(document_id)

    def publish(self, document_id: str, *, actor: str) -> Document:
        """Make a draft searchable. Needs a recorded license (see ADR-011)."""
        document = self._require(document_id)
        if document.status is DocumentStatus.PUBLISHED:
            return document
        if not (document.license and document.license.strip()):
            raise PublishBlockedError(
                "Record the document's license before publishing (see ADR-011)."
            )

        chunks = self._repository.get_chunks(document_id)
        vectors = self._embedder.embed(
            [searchable_text(document.title, c.section_path, c.text) for c in chunks]
        )
        items = [
            IndexItem(chunk.id, document_id, vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            self._index.upsert(items)
            self._repository.transition(
                document_id, DocumentStatus.PUBLISHED, actor=actor, when=datetime.now(UTC)
            )
        except Exception:
            # Leave nothing half-published: remove any vectors we just added.
            self._index.delete_document(document_id)
            raise
        return self._require(document_id)

    def unpublish(self, document_id: str, *, actor: str) -> Document:
        """Take a document out of search. It is kept, marked retired, for the audit trail."""
        document = self._require(document_id)
        if document.status is not DocumentStatus.PUBLISHED:
            return document
        self._index.delete_document(document_id)
        self._repository.transition(
            document_id, DocumentStatus.RETIRED, actor=actor, when=datetime.now(UTC)
        )
        return self._require(document_id)

    def _require(self, document_id: str) -> Document:
        document = self._repository.get_document(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document
