from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from citedesk.storage.repository import SqlRepository


def test_sqlite_enforces_foreign_keys_like_postgres(tmp_path: Path) -> None:
    """A chunk without its document must be refused. SQLite skips this check unless enabled."""
    repository = SqlRepository.from_url(f"sqlite:///{tmp_path / 'fk.db'}")
    with repository._sessions.begin() as session, pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO chunks (id, document_id, ordinal, section_path, text) VALUES (:i, :d, 0, 's', 't')"
            ),
            {"i": "c1", "d": "no-such-document"},
        )


def test_an_empty_database_has_no_documents_and_version_zero(tmp_path: Path) -> None:
    repository = SqlRepository.from_url(f"sqlite:///{tmp_path / 'empty.db'}")
    assert repository.list_documents() == []
    assert repository.corpus_version() == 0
    assert repository.audit_log() == []


def test_transition_of_an_unknown_document_raises(tmp_path: Path) -> None:
    from citedesk.domain.models import DocumentStatus

    repository = SqlRepository.from_url(f"sqlite:///{tmp_path / 'x.db'}")
    with pytest.raises(KeyError):
        repository.transition(
            "missing", DocumentStatus.PUBLISHED, actor="tester", when=datetime.now(UTC)
        )
