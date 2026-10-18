"""SQL storage for documents, chunks, the audit log and the corpus version.

One implementation serves both SQLite (local) and Postgres (deployed): only the
connection URL differs. It implements `DocumentRepository` (used by ingestion) and
`CorpusReader` (used by the answer flow).

Schema creation here is a stand-in for real migrations, which come in a later ticket.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from citedesk.domain.models import AuditEntry, Chunk, Document, DocumentStatus, Passage


class _Base(DeclarativeBase):
    pass


class _DocumentRow(_Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    source_name: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    license: Mapped[str | None] = mapped_column(String(300))
    terms_url: Mapped[str | None] = mapped_column(String(2000))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class _ChunkRow(_Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    section_path: Mapped[str] = mapped_column(String(1000))
    text: Mapped[str] = mapped_column(Text)


class _AuditRow(_Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(50))
    target: Mapped[str] = mapped_column(String(200))


class _CorpusStateRow(_Base):
    """A single row holding the corpus version. It changes whenever published content changes."""

    __tablename__ = "corpus_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


_CORPUS_STATE_ID = 1


def _enforce_sqlite_foreign_keys(connection: Any, _record: Any) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything we store is UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _to_document(row: _DocumentRow) -> Document:
    return Document(
        id=row.id,
        title=row.title,
        source_name=row.source_name,
        source_url=row.source_url,
        license=row.license,
        terms_url=row.terms_url,
        content_hash=row.content_hash,
        status=DocumentStatus(row.status),
        created_at=_as_utc(row.created_at) or row.created_at,
        published_at=_as_utc(row.published_at),
    )


def _to_chunk(row: _ChunkRow) -> Chunk:
    return Chunk(
        id=row.id,
        document_id=row.document_id,
        ordinal=row.ordinal,
        section_path=row.section_path,
        text=row.text,
    )


class SqlRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, database_url: str) -> "SqlRepository":
        engine = create_engine(database_url)
        if engine.dialect.name == "sqlite":
            # SQLite ignores foreign keys unless asked, which hid an insert-order bug that
            # Postgres caught. Enforce them so local runs and tests behave like production.
            event.listen(engine, "connect", _enforce_sqlite_foreign_keys)
        _Base.metadata.create_all(engine)
        return cls(engine)

    # --- write side (DocumentRepository) -------------------------------------------------

    def add_document(self, document: Document, chunks: Sequence[Chunk], *, actor: str) -> None:
        with self._sessions.begin() as session:
            session.add(_DocumentRow(**document.model_dump(mode="python", exclude_none=False)))
            session.flush()  # the document must exist before its chunks (Postgres enforces this)
            session.add_all(
                _ChunkRow(
                    id=c.id,
                    document_id=c.document_id,
                    ordinal=c.ordinal,
                    section_path=c.section_path,
                    text=c.text,
                )
                for c in chunks
            )
            self._write_audit(session, document.created_at, actor, "add", document.id)

    def get_document(self, document_id: str) -> Document | None:
        with self._sessions() as session:
            row = session.get(_DocumentRow, document_id)
            return _to_document(row) if row else None

    def find_by_hash(self, content_hash: str) -> Document | None:
        with self._sessions() as session:
            row = session.scalars(
                select(_DocumentRow).where(_DocumentRow.content_hash == content_hash)
            ).first()
            return _to_document(row) if row else None

    def get_chunks(self, document_id: str) -> list[Chunk]:
        with self._sessions() as session:
            rows = session.scalars(
                select(_ChunkRow)
                .where(_ChunkRow.document_id == document_id)
                .order_by(_ChunkRow.ordinal)
            )
            return [_to_chunk(row) for row in rows]

    def list_documents(self) -> list[Document]:
        with self._sessions() as session:
            rows = session.scalars(select(_DocumentRow).order_by(_DocumentRow.created_at))
            return [_to_document(row) for row in rows]

    def update_license(
        self, document_id: str, *, license: str, terms_url: str | None, actor: str, when: datetime
    ) -> None:
        with self._sessions.begin() as session:
            row = session.get(_DocumentRow, document_id)
            if row is None:
                raise KeyError(document_id)
            row.license = license
            row.terms_url = terms_url
            self._write_audit(session, when, actor, "license", document_id)

    def transition(
        self, document_id: str, status: DocumentStatus, *, actor: str, when: datetime
    ) -> None:
        with self._sessions.begin() as session:
            row = session.get(_DocumentRow, document_id)
            if row is None:
                raise KeyError(document_id)
            row.status = status.value
            if status is DocumentStatus.PUBLISHED:
                row.published_at = when
            self._bump_corpus_version(session)
            self._write_audit(session, when, actor, status.value, document_id)

    # --- read side (CorpusReader) --------------------------------------------------------

    def corpus_version(self) -> int:
        with self._sessions() as session:
            state = session.get(_CorpusStateRow, _CORPUS_STATE_ID)
            return state.version if state else 0

    def published_passages(self) -> list[Passage]:
        statement = (
            select(_ChunkRow, _DocumentRow.title)
            .join(_DocumentRow, _ChunkRow.document_id == _DocumentRow.id)
            .where(_DocumentRow.status == DocumentStatus.PUBLISHED.value)
            .order_by(_DocumentRow.created_at, _ChunkRow.ordinal)
        )
        with self._sessions() as session:
            return [_to_passage(chunk, title) for chunk, title in session.execute(statement)]

    def get_passage(self, chunk_id: str) -> Passage | None:
        statement = (
            select(_ChunkRow, _DocumentRow.title)
            .join(_DocumentRow, _ChunkRow.document_id == _DocumentRow.id)
            .where(_ChunkRow.id == chunk_id)
            .where(_DocumentRow.status == DocumentStatus.PUBLISHED.value)
        )
        with self._sessions() as session:
            found = session.execute(statement).first()
            return _to_passage(found[0], found[1]) if found else None

    # --- helpers -------------------------------------------------------------------------

    def audit_log(self, limit: int = 100) -> list[AuditEntry]:
        """The most recent audit entries, newest first."""
        with self._sessions() as session:
            rows = session.scalars(select(_AuditRow).order_by(_AuditRow.id.desc()).limit(limit))
            return [
                AuditEntry(
                    at=_as_utc(row.at) or row.at,
                    actor=row.actor,
                    action=row.action,
                    target=row.target,
                )
                for row in rows
            ]

    def audit_actions(self, target: str) -> list[str]:
        """Audit actions recorded for one target, oldest first (used by tests and the admin UI)."""
        with self._sessions() as session:
            rows = session.scalars(
                select(_AuditRow).where(_AuditRow.target == target).order_by(_AuditRow.id)
            )
            return [row.action for row in rows]

    @staticmethod
    def _bump_corpus_version(session: Session) -> None:
        state = session.get(_CorpusStateRow, _CORPUS_STATE_ID)
        if state is None:
            session.add(_CorpusStateRow(id=_CORPUS_STATE_ID, version=1))
        else:
            state.version += 1

    @staticmethod
    def _write_audit(
        session: Session, when: datetime, actor: str, action: str, target: str
    ) -> None:
        session.add(_AuditRow(at=when, actor=actor, action=action, target=target))


def _to_passage(chunk: _ChunkRow, document_title: str) -> Passage:
    return Passage(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        document_title=document_title,
        section_path=chunk.section_path,
        text=chunk.text,
    )
