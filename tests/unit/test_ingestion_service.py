from collections.abc import Sequence

import httpx
import pytest

from citedesk.bootstrap import App
from citedesk.domain.models import DocumentStatus
from citedesk.domain.ports import IndexItem
from citedesk.ingestion.fetching import UrlFetcher
from citedesk.ingestion.parsing import ParseError
from citedesk.ingestion.service import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    IngestionService,
    PublishBlockedError,
)
from citedesk.storage.dev_adapters import HashingEmbedder, InMemoryVectorIndex
from tests.conftest import SAMPLE_HANDBOOK


def _add(app: App, *, license: str | None = "CC0", content: str = SAMPLE_HANDBOOK):  # type: ignore[no-untyped-def]
    return app.ingestion.add_text(
        content,
        content_type="markdown",
        title="Acme Handbook",
        source_name="tests",
        actor="tester",
        license=license,
    )


def test_a_new_document_is_a_draft_and_is_not_searchable(app: App) -> None:
    document = _add(app)
    assert document.status is DocumentStatus.DRAFT
    assert app.repository.published_passages() == []
    assert app.answers.ask("How many vacation days do I get?").refused


def test_preview_shows_chunks_with_their_sections(app: App) -> None:
    document = _add(app)
    sections = [chunk.section_path for chunk in app.ingestion.preview(document.id)]
    assert "Time off > Vacation" in sections


def test_adding_the_same_content_twice_is_refused(app: App) -> None:
    first = _add(app)
    with pytest.raises(DuplicateDocumentError) as error:
        _add(app)
    assert error.value.existing.id == first.id


def test_content_with_too_little_text_is_refused(app: App) -> None:
    with pytest.raises(ParseError):
        _add(app, content="# Access denied")


def test_publishing_requires_a_recorded_license(app: App) -> None:
    document = _add(app, license=None)
    with pytest.raises(PublishBlockedError):
        app.ingestion.publish(document.id, actor="tester")
    assert app.repository.published_passages() == []


def test_publish_makes_the_document_searchable_and_bumps_the_corpus_version(app: App) -> None:
    document = _add(app)
    before = app.repository.corpus_version()
    published = app.ingestion.publish(document.id, actor="tester")
    assert published.status is DocumentStatus.PUBLISHED
    assert published.published_at is not None
    assert app.repository.corpus_version() == before + 1
    assert app.repository.published_passages()


def test_publishing_twice_changes_nothing(app: App) -> None:
    document = _add(app)
    app.ingestion.publish(document.id, actor="tester")
    version = app.repository.corpus_version()
    app.ingestion.publish(document.id, actor="tester")
    assert app.repository.corpus_version() == version


def test_unpublish_removes_the_document_from_search_but_keeps_it(published_app: App) -> None:
    document = published_app.repository.list_documents()[0]
    published_app.ingestion.unpublish(document.id, actor="tester")
    assert published_app.repository.get_document(document.id) is not None
    assert published_app.repository.published_passages() == []
    assert published_app.answers.ask("How many vacation days do I get?").refused


def test_every_step_is_written_to_the_audit_log(app: App) -> None:
    document = _add(app)
    app.ingestion.publish(document.id, actor="tester")
    app.ingestion.unpublish(document.id, actor="tester")
    assert app.repository.audit_actions(document.id) == ["add", "published", "retired"]


def test_unknown_document_ids_raise(app: App) -> None:
    with pytest.raises(DocumentNotFoundError):
        app.ingestion.publish("nope", actor="tester")


def test_url_import_adds_a_draft_with_the_page_url(app: App) -> None:
    page = (
        "<html><body><h1>Remote Work</h1><p>Employees may work remotely up to three days a week "
        "with manager approval. Remote work needs a secure home network.</p></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    fetcher = UrlFetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda host: ["93.184.216.34"],
    )
    ingestion = IngestionService(app.repository, HashingEmbedder(), InMemoryVectorIndex(), fetcher)

    document = ingestion.add_url(
        "https://example.com/remote", source_name="Example", actor="tester", license="CC0"
    )

    assert document.status is DocumentStatus.DRAFT
    assert document.source_url == "https://example.com/remote"
    assert document.title == "Remote Work"


def test_url_import_needs_a_fetcher(app: App) -> None:
    ingestion = IngestionService(app.repository, HashingEmbedder(), InMemoryVectorIndex())
    with pytest.raises(RuntimeError, match="not configured"):
        ingestion.add_url("https://example.com", source_name="x", actor="tester")


class _BrokenIndex:
    def __init__(self) -> None:
        self.cleaned_up: list[str] = []

    def upsert(self, items: Sequence[IndexItem]) -> None:
        raise ConnectionError("vector database is down")

    def delete_document(self, document_id: str) -> None:
        self.cleaned_up.append(document_id)

    def search(self, vector: Sequence[float], limit: int) -> list[tuple[str, float]]:
        return []


def test_a_failed_index_update_leaves_the_document_unpublished(app: App) -> None:
    index = _BrokenIndex()
    ingestion = IngestionService(app.repository, HashingEmbedder(), index)
    document = _add(app)

    with pytest.raises(ConnectionError):
        ingestion.publish(document.id, actor="tester")

    assert app.repository.get_document(document.id).status is DocumentStatus.DRAFT  # type: ignore[union-attr]
    assert app.repository.corpus_version() == 0
    assert index.cleaned_up == [document.id]


def test_unpublishing_a_draft_changes_nothing(app: App) -> None:
    document = _add(app)
    assert app.ingestion.unpublish(document.id, actor="tester").status is DocumentStatus.DRAFT


def test_the_admins_title_wins_over_the_title_in_the_file(app: App) -> None:
    document = app.ingestion.add_text(
        SAMPLE_HANDBOOK,
        content_type="markdown",
        title="My own name for it",
        source_name="tests",
        actor="tester",
        license="CC0",
    )
    assert document.title == "My own name for it"


def test_without_a_title_the_one_in_the_file_is_used(app: App) -> None:
    document = app.ingestion.add_text(
        SAMPLE_HANDBOOK,
        content_type="markdown",
        title=None,
        source_name="tests",
        actor="tester",
        license="CC0",
    )
    assert document.title == "Acme Handbook"
