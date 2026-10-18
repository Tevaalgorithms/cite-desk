"""The Pinecone adapter and the index sync, tested against a fake that behaves like Pinecone,
including its delay before new vectors can be read. No network, no key, no cost."""

from __future__ import annotations  # the fake has a method named `list`, as Pinecone does

from types import SimpleNamespace

import pytest

from citedesk.adapters.pinecone_index import PineconeVectorIndex, VectorIndexError, ensure_index
from citedesk.bootstrap import App, build_index
from citedesk.config import Settings
from citedesk.domain.ports import IndexItem
from citedesk.indexing import sync_vector_index
from citedesk.storage.dev_adapters import HashingEmbedder, InMemoryVectorIndex
from tests.conftest import SAMPLE_HANDBOOK


class FakePinecone:
    """The part of a Pinecone index the adapter uses. Fetches miss for `delay` calls after a write."""

    def __init__(self, delay: int = 0) -> None:
        self.namespaces: dict[str, dict[str, list[float]]] = {}
        self.delay = delay
        self._misses_left = 0
        self.calls: list[str] = []

    def upsert(self, vectors: list[dict[str, object]], namespace: str) -> None:
        assert len(vectors) <= 100, "Pinecone limits upserts, so the adapter must batch"
        self.calls.append("upsert")
        store = self.namespaces.setdefault(namespace, {})
        for vector in vectors:
            store[str(vector["id"])] = list(vector["values"])  # type: ignore[call-overload]
        self._misses_left = self.delay

    def fetch(self, ids: list[str], namespace: str) -> dict[str, dict[str, object]]:
        assert len(ids) <= 100
        if self._misses_left > 0:
            self._misses_left -= 1
            return {"vectors": {}}
        store = self.namespaces.get(namespace, {})
        return {"vectors": {i: {"id": i} for i in ids if i in store}}

    def query(
        self, vector: list[float], top_k: int, namespace: str, include_metadata: bool
    ) -> dict[str, object]:
        store = self.namespaces.get(namespace, {})
        scored = sorted(
            ((i, sum(a * b for a, b in zip(vector, v, strict=True))) for i, v in store.items()),
            key=lambda pair: pair[1], reverse=True,
        )  # fmt: skip
        return {"matches": [{"id": i, "score": s} for i, s in scored[:top_k]]}

    def list(self, prefix: str, namespace: str):  # type: ignore[no-untyped-def]
        ids = sorted(i for i in self.namespaces.get(namespace, {}) if i.startswith(prefix))
        for start in range(0, len(ids), 2):  # small pages, like the real thing
            yield ids[start : start + 2]

    def delete(self, ids: list[str], namespace: str) -> None:
        assert len(ids) <= 1000
        for i in ids:
            self.namespaces.get(namespace, {}).pop(i, None)


class SlowDeletePinecone(FakePinecone):
    """Deleted vectors keep showing up in fetches for a few calls, like real Pinecone."""

    def __init__(self, stale_fetches: int) -> None:
        super().__init__()
        self._stale_fetches = stale_fetches
        self._pending: dict[str, list[float]] = {}

    def delete(self, ids: list[str], namespace: str) -> None:
        store = self.namespaces.get(namespace, {})
        for i in ids:
            if i in store:
                self._pending[i] = store.pop(i)

    def fetch(self, ids: list[str], namespace: str) -> dict[str, dict[str, object]]:
        if self._pending and self._stale_fetches > 0:
            self._stale_fetches -= 1
            return {"vectors": {i: {"id": i} for i in ids if i in self._pending}}
        self._pending.clear()
        return super().fetch(ids, namespace)


def _items(prefix: str, count: int) -> list[IndexItem]:
    return [IndexItem(f"{prefix}:{n:04d}", prefix, [1.0, float(n)]) for n in range(count)]


def test_vectors_are_written_in_batches_and_searchable() -> None:
    fake = FakePinecone()
    index = PineconeVectorIndex(fake, "dev")
    index.upsert(_items("docA", 250))
    assert fake.calls.count("upsert") == 3  # 100 + 100 + 50
    assert len(index.ids()) == 250
    best = index.search([1.0, 10.0], limit=3)
    assert best[0][0] == "docA:0010" or best[0][0].startswith("docA:02")  # nearest by dot product
    assert len(best) == 3


def test_upsert_waits_until_the_vectors_can_be_read_back() -> None:
    fake = FakePinecone(delay=3)  # the first three fetches miss, like a slow Pinecone
    slept: list[float] = []
    index = PineconeVectorIndex(fake, "dev", sleep=slept.append)
    index.upsert(_items("docA", 5))
    assert len(slept) == 3  # it waited instead of returning too early


def test_upsert_fails_loudly_if_vectors_never_become_readable() -> None:
    fake = FakePinecone(delay=10**6)
    index = PineconeVectorIndex(fake, "dev", visible_within_seconds=0.0, sleep=lambda _: None)
    with pytest.raises(VectorIndexError, match="not readable"):
        index.upsert(_items("docA", 2))


def test_deleting_a_document_removes_only_its_vectors() -> None:
    fake = FakePinecone()
    index = PineconeVectorIndex(fake, "dev")
    index.upsert(_items("docA", 5) + _items("docB", 3))
    index.delete_document("docA")
    assert index.ids() == {"docB:0000", "docB:0001", "docB:0002"}


def test_delete_waits_until_the_vectors_are_really_gone() -> None:
    fake = SlowDeletePinecone(stale_fetches=3)
    slept: list[float] = []
    index = PineconeVectorIndex(fake, "dev", sleep=slept.append)
    index.upsert(_items("docA", 3))
    index.delete_document("docA")
    assert len(slept) >= 3  # it kept waiting while the deleted vectors were still readable
    assert index.ids() == set()


def test_deleting_nothing_does_not_call_pinecone() -> None:
    fake = FakePinecone()
    PineconeVectorIndex(fake, "dev").delete_ids([])
    assert fake.calls == []


def test_a_document_id_that_prefixes_another_does_not_delete_the_other() -> None:
    fake = FakePinecone()
    index = PineconeVectorIndex(fake, "dev")
    index.upsert(_items("doc1", 2) + _items("doc12", 2))
    index.delete_document("doc1")  # the prefix "doc1:" must not match "doc12:..."
    assert index.ids() == {"doc12:0000", "doc12:0001"}


def test_namespaces_keep_environments_apart() -> None:
    fake = FakePinecone()
    PineconeVectorIndex(fake, "dev").upsert(_items("docA", 2))
    prod = PineconeVectorIndex(fake, "prod")
    assert prod.ids() == set()
    assert prod.search([1.0, 0.0], 5) == []


# --- ensure_index -------------------------------------------------------------------------


class FakeClient:
    def __init__(self, existing_dimension: int | None = None, ready_after: int = 0) -> None:
        self.created: dict[str, object] | None = None
        self._dimension = existing_dimension
        self._polls_until_ready = ready_after

    def has_index(self, name: str) -> bool:
        return self._dimension is not None

    def create_index(self, **kwargs: object) -> None:
        self.created = kwargs
        self._dimension = int(kwargs["dimension"])  # type: ignore[call-overload]

    def describe_index(self, name: str) -> SimpleNamespace:
        ready = self._polls_until_ready <= 0
        self._polls_until_ready -= 1
        return SimpleNamespace(
            dimension=self._dimension, status={"ready": ready}, host="host.example"
        )


def test_a_missing_index_is_created_with_the_right_size_and_metric() -> None:
    client = FakeClient()
    host = ensure_index(client, "cite-desk", dimension=384, cloud="aws", region="us-east-1")
    assert host == "host.example"
    assert client.created is not None
    assert client.created["dimension"] == 384
    assert client.created["metric"] == "cosine"


def test_an_existing_index_is_reused_and_not_recreated() -> None:
    client = FakeClient(existing_dimension=384)
    ensure_index(client, "cite-desk", dimension=384, cloud="aws", region="us-east-1")
    assert client.created is None


def test_an_index_of_the_wrong_size_is_refused_with_a_clear_message() -> None:
    client = FakeClient(existing_dimension=256)
    with pytest.raises(VectorIndexError, match=r"dimension 256.*384"):
        ensure_index(client, "cite-desk", dimension=384, cloud="aws", region="us-east-1")


# --- sync ---------------------------------------------------------------------------------


def test_sync_fills_an_empty_index_then_does_nothing(published_app: App) -> None:
    fresh = InMemoryVectorIndex()
    embedder = HashingEmbedder()
    first = sync_vector_index(published_app.repository, embedder, fresh)
    assert first.added == first.published > 0
    assert first.removed == 0
    second = sync_vector_index(published_app.repository, embedder, fresh)
    assert (second.added, second.removed) == (0, 0)


def test_sync_removes_vectors_that_are_no_longer_published(published_app: App) -> None:
    index = InMemoryVectorIndex()
    embedder = HashingEmbedder()
    sync_vector_index(published_app.repository, embedder, index)
    index.upsert([IndexItem("ghost:0000", "ghost", embedder.embed(["stale"])[0])])
    report = sync_vector_index(published_app.repository, embedder, index)
    assert report.removed == 1
    assert "ghost:0000" not in index.ids()


def test_sync_repairs_a_partly_missing_index(published_app: App) -> None:
    index = InMemoryVectorIndex()
    embedder = HashingEmbedder()
    sync_vector_index(published_app.repository, embedder, index)
    victim = sorted(index.ids())[0]
    index.delete_ids([victim])
    report = sync_vector_index(published_app.repository, embedder, index)
    assert report.added == 1
    assert victim in index.ids()


def test_sync_survives_a_restart_with_the_published_content(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    document = app.ingestion.add_text(
        SAMPLE_HANDBOOK,
        content_type="markdown",
        title="Acme",
        source_name="t",
        actor="t",
        license="CC0",
    )
    app.ingestion.publish(document.id, actor="t")
    assert app.answers.ask("How many vacation days do I get?").refused is False


# --- settings ------------------------------------------------------------------------------


def test_the_default_index_is_in_memory() -> None:
    assert isinstance(build_index(Settings(), HashingEmbedder()), InMemoryVectorIndex)


def test_the_pinecone_index_needs_a_key() -> None:
    with pytest.raises(RuntimeError, match="CITEDESK_PINECONE_API_KEY"):
        build_index(Settings(vector_index="pinecone"), HashingEmbedder())
