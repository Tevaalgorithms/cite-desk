"""Plain data objects shared by ingestion and the answer flow.

These are the only things the two sides have in common, besides the interfaces in `ports.py`.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DocumentStatus(StrEnum):
    DRAFT = "draft"  # added by an admin, invisible to users
    PUBLISHED = "published"  # searchable
    RETIRED = "retired"  # taken down, kept for the audit trail


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Document(_Frozen):
    id: str
    title: str
    source_name: str
    source_url: str | None = None
    license: str | None = None
    terms_url: str | None = None
    content_hash: str
    status: DocumentStatus = DocumentStatus.DRAFT
    created_at: datetime
    published_at: datetime | None = None


class Chunk(_Frozen):
    """A passage-sized piece of a document."""

    id: str
    document_id: str
    ordinal: int
    section_path: str  # e.g. "Benefits > Parental leave"
    text: str


class AuditEntry(_Frozen):
    """One recorded admin action."""

    at: datetime
    actor: str
    action: str
    target: str


class Passage(_Frozen):
    """A chunk as the answer flow sees it: with its document title and a relevance score."""

    chunk_id: str
    document_id: str
    document_title: str
    section_path: str
    text: str
    score: float = 0.0


class Citation(_Frozen):
    marker: int  # the [n] shown in the answer
    chunk_id: str
    document_title: str
    section_path: str
    quote: str  # the cited passage text, for the source drawer


class Answer(_Frozen):
    question: str
    text: str = ""  # empty when refused
    citations: tuple[Citation, ...] = ()
    refused: bool = False
    refusal_reason: str | None = None
    corpus_version: int = 0


def searchable_text(document_title: str, section_path: str, text: str) -> str:
    """The text that keyword and vector search index for a chunk.

    Ingestion (when embedding at publish time) and the answer flow (when building the
    keyword index) must use this same function so both searches see the same words.
    """
    return f"{document_title}. {section_path}. {text}"
