"""The same workflow as the unit tests, on a real Postgres.

Skipped unless CITEDESK_TEST_POSTGRES_URL is set, for example:
    docker run -d --rm --name citedesk-pg -e POSTGRES_PASSWORD=<pick one> -p 55432:5432 postgres:16-alpine
    export CITEDESK_TEST_POSTGRES_URL="postgresql+psycopg://postgres:<same>@localhost:55432/postgres"
    uv sync --extra postgres && uv run pytest tests/integration
Each test runs in its own schema, so tests never see each other's data.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from citedesk.bootstrap import App, build_app
from citedesk.config import Settings
from citedesk.domain.models import DocumentStatus
from citedesk.ingestion.service import DuplicateDocumentError
from tests.conftest import SAMPLE_HANDBOOK

POSTGRES_URL = os.environ.get("CITEDESK_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not POSTGRES_URL, reason="CITEDESK_TEST_POSTGRES_URL is not set"),
]


@pytest.fixture
def pg_app() -> Iterator[App]:
    assert POSTGRES_URL
    schema = f"test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    separator = "&" if "?" in POSTGRES_URL else "?"
    url = f"{POSTGRES_URL}{separator}options=-csearch_path%3D{schema}"
    try:
        yield build_app(Settings(database_url=url))
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _add(app: App, license: str | None = "CC0"):  # type: ignore[no-untyped-def]
    return app.ingestion.add_text(
        SAMPLE_HANDBOOK,
        content_type="markdown",
        title="Acme Handbook",
        source_name="tests",
        actor="tester",
        license=license,
    )


def test_add_publish_ask_cite_unpublish_on_postgres(pg_app: App) -> None:
    document = _add(pg_app)
    assert document.status is DocumentStatus.DRAFT
    assert pg_app.answers.ask("How many vacation days do I get?").refused

    published = pg_app.ingestion.publish(document.id, actor="tester")
    assert published.status is DocumentStatus.PUBLISHED
    assert published.published_at is not None
    assert published.published_at.tzinfo is not None  # timezone survives the round trip

    answer = pg_app.answers.ask("How many vacation days do I get?")
    assert not answer.refused
    assert "20 days" in answer.text
    assert answer.citations[0].section_path == "Time off > Vacation"
    assert pg_app.answers.source_passage(answer.citations[0].chunk_id) is not None

    pg_app.ingestion.unpublish(document.id, actor="tester")
    assert pg_app.answers.ask("How many vacation days do I get?").refused
    assert pg_app.answers.source_passage(answer.citations[0].chunk_id) is None


def test_duplicate_content_is_refused_on_postgres(pg_app: App) -> None:
    first = _add(pg_app)
    with pytest.raises(DuplicateDocumentError) as error:
        _add(pg_app)
    assert error.value.existing.id == first.id


def test_corpus_version_and_audit_log_on_postgres(pg_app: App) -> None:
    document = _add(pg_app)
    assert pg_app.repository.corpus_version() == 0
    pg_app.ingestion.publish(document.id, actor="alice")
    pg_app.ingestion.unpublish(document.id, actor="bob")
    assert pg_app.repository.corpus_version() == 2
    entries = pg_app.repository.audit_log()
    assert [(e.actor, e.action) for e in entries] == [
        ("bob", "retired"),
        ("alice", "published"),
        ("tester", "add"),
    ]
    assert entries[0].at.tzinfo is not None


def test_chunks_keep_their_order_and_text_on_postgres(pg_app: App) -> None:
    document = _add(pg_app)
    chunks = pg_app.repository.get_chunks(document.id)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert any(c.section_path == "Time off > Vacation" and "20 days" in c.text for c in chunks)
