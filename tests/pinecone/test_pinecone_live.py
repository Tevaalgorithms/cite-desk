"""Tests against the real Pinecone index. They use a random throwaway namespace and clean it up.

    CITEDESK_RUN_PINECONE_TESTS=1 uv run --extra models pytest tests/pinecone --no-cov

The index is created once with `uv run citedesk pinecone init`. Pinecone's free plan is generous
but not unlimited, so these run only on request, never in CI.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr

from citedesk.adapters.pinecone_index import PineconeVectorIndex
from citedesk.bootstrap import App, build_app, build_models
from citedesk.config import Settings
from citedesk.indexing import sync_vector_index
from citedesk.ops.ssm import read_env_file
from pinecone import Pinecone

ROOT = Path(__file__).resolve().parents[2]
_ENV = read_env_file(ROOT / ".env") if (ROOT / ".env").exists() else {}
_KEY = _ENV.get("CITEDESK_PINECONE_API_KEY", "")

pytestmark = [
    pytest.mark.pinecone,
    pytest.mark.skipif(
        os.environ.get("CITEDESK_RUN_PINECONE_TESTS") != "1" or not _KEY,
        reason="set CITEDESK_RUN_PINECONE_TESTS=1 and CITEDESK_PINECONE_API_KEY in .env to run",
    ),
]
HANDBOOK = (ROOT / "data" / "sample" / "acme-handbook.md").read_text()


@pytest.fixture
def namespace() -> Iterator[str]:
    name = f"test-{uuid.uuid4().hex[:10]}"
    yield name
    client = Pinecone(api_key=_KEY)
    host = client.describe_index("cite-desk").host
    client.Index(host=host).delete(delete_all=True, namespace=name)


@pytest.fixture
def live_app(tmp_path: Path, namespace: str) -> App:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'p.db'}",
        models="local",
        vector_index="pinecone",
        pinecone_api_key=SecretStr(_KEY),
        pinecone_index="cite-desk",
        pinecone_namespace=namespace,
    )
    return build_app(settings)


def _publish(app: App) -> str:
    document = app.ingestion.add_text(
        HANDBOOK, content_type="markdown", title=None, source_name="live test",
        actor="tester", license="CC0 (synthetic sample)",
    )  # fmt: skip
    app.ingestion.publish(document.id, actor="tester")
    return document.id


def test_publish_ask_and_unpublish_through_the_real_index(live_app: App) -> None:
    assert isinstance(live_app.index, PineconeVectorIndex)
    assert live_app.index.ids() == set()  # a fresh namespace

    document_id = _publish(live_app)
    stored = live_app.index.ids()
    assert len(stored) == len(live_app.repository.published_passages()) > 0
    assert all(chunk_id.startswith(f"{document_id}:") for chunk_id in stored)

    answer = live_app.answers.ask("How much time off do I get when I have a baby?")
    assert not answer.refused, answer.refusal_reason
    assert answer.citations[0].section_path == "Time off > Parental leave"

    live_app.ingestion.unpublish(document_id, actor="tester")
    assert live_app.answers.ask("How many vacation days do I get?").refused


def test_a_new_process_finds_the_vectors_already_there(
    live_app: App, tmp_path: Path, namespace: str
) -> None:
    _publish(live_app)
    embedder, _ = build_models(Settings(models="local"))
    # a second "process" over the same database and the same Pinecone namespace
    report = sync_vector_index(live_app.repository, embedder, live_app.index)
    assert (report.added, report.removed) == (0, 0)  # nothing to re-embed: vectors survived


def test_sync_repairs_a_vector_that_went_missing(live_app: App) -> None:
    _publish(live_app)
    victim = sorted(live_app.index.ids())[0]
    live_app.index.delete_ids([victim])
    embedder, _ = build_models(Settings(models="local"))
    report = sync_vector_index(live_app.repository, embedder, live_app.index)
    assert report.added == 1
    assert victim in live_app.index.ids()


def test_two_namespaces_do_not_see_each_other(live_app: App) -> None:
    _publish(live_app)
    other = PineconeVectorIndex(live_app.index._index, f"other-{uuid.uuid4().hex[:6]}")  # type: ignore[attr-defined]
    assert other.ids() == set()
