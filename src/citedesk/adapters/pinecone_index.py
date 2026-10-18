"""A vector index kept in Pinecone, so vectors survive restarts.

The database stays the source of truth: this index is a searchable copy that can always be rebuilt
from the stored chunks (see `sync_vector_index`). Pinecone is eventually consistent, which shapes
three behaviours here:
  * after writing, `upsert` waits until the vectors can really be read back before returning;
  * deleted vectors may linger for a moment, so the answer flow only trusts ids that are published;
  * `ensure_index` and `sync_vector_index` are safe to run repeatedly.
"""

import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from citedesk.domain.ports import IndexItem

_UPSERT_BATCH = 100
_DELETE_BATCH = 500


class VectorIndexError(RuntimeError):
    """The vector index could not be used. The message never contains a key."""


class PineconeVectorIndex:
    def __init__(
        self,
        index: Any,
        namespace: str,
        *,
        visible_within_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._index = index
        self._namespace = namespace
        self._visible_within = visible_within_seconds
        self._sleep = sleep

    # --- VectorIndex -----------------------------------------------------------------------

    def upsert(self, items: Sequence[IndexItem]) -> None:
        for start in range(0, len(items), _UPSERT_BATCH):
            batch = items[start : start + _UPSERT_BATCH]
            self._index.upsert(
                vectors=[
                    {
                        "id": i.chunk_id,
                        "values": list(i.vector),
                        "metadata": {"document_id": i.document_id},
                    }
                    for i in batch
                ],
                namespace=self._namespace,
            )
        self._wait_until_visible([item.chunk_id for item in items])

    def delete_document(self, document_id: str) -> None:
        # Chunk ids look like "<document id>:<number>", so a prefix finds a document's vectors.
        self.delete_ids(list(self._ids_with_prefix(f"{document_id}:")))

    def ids(self) -> set[str]:
        return set(self._ids_with_prefix(""))

    def delete_ids(self, chunk_ids: Sequence[str]) -> None:
        for start in range(0, len(chunk_ids), _DELETE_BATCH):
            self._index.delete(
                ids=list(chunk_ids[start : start + _DELETE_BATCH]), namespace=self._namespace
            )
        self._wait_until_gone(list(chunk_ids))

    def search(self, vector: Sequence[float], limit: int) -> list[tuple[str, float]]:
        response = self._index.query(
            vector=list(vector), top_k=limit, namespace=self._namespace, include_metadata=False
        )
        return [(match["id"], float(match["score"])) for match in response["matches"]]

    # --- helpers ---------------------------------------------------------------------------

    def _ids_with_prefix(self, prefix: str) -> Iterable[str]:
        for page in self._index.list(prefix=prefix, namespace=self._namespace):
            yield from page

    def _wait_until_visible(self, chunk_ids: Sequence[str]) -> None:
        """Pinecone accepts a write before it can be read. Wait until all ids can be fetched."""
        self._wait_for(chunk_ids, present=True, what="readable")

    def _wait_until_gone(self, chunk_ids: Sequence[str]) -> None:
        """Deletes are also delayed. Wait until none of the ids can be fetched or listed."""
        self._wait_for(chunk_ids, present=False, what="deleted")

    def _wait_for(self, chunk_ids: Sequence[str], *, present: bool, what: str) -> None:
        if not chunk_ids:
            return
        deadline = time.monotonic() + self._visible_within
        while True:
            found: set[str] = set()
            for start in range(0, len(chunk_ids), 100):
                fetched = self._index.fetch(
                    ids=list(chunk_ids[start : start + 100]), namespace=self._namespace
                )
                found.update(fetched["vectors"])
            wanted = set(chunk_ids)
            # for deletes also check the listing, which can lag behind fetch
            listed = (
                set() if present else wanted & set(self._ids_with_prefix(_common_prefix(chunk_ids)))
            )
            unsettled = (wanted - found) if present else (found | listed)
            if not unsettled:
                return
            if time.monotonic() > deadline:
                waited = f"{self._visible_within:.0f} s"
                raise VectorIndexError(
                    f"{len(unsettled)} vectors were not {what} {waited} after the change"
                )
            self._sleep(0.5)


def _common_prefix(chunk_ids: Sequence[str]) -> str:
    """The longest shared start of the ids (for example "<document id>:"), to narrow a listing."""
    first, last = min(chunk_ids), max(chunk_ids)
    length = 0
    while length < min(len(first), len(last)) and first[length] == last[length]:
        length += 1
    return first[:length]


def ensure_index(
    client: Any, name: str, *, dimension: int, cloud: str, region: str, wait_seconds: float = 120.0
) -> str:
    """Create the index if it does not exist, and return its host. Refuses a wrong-sized index."""
    from pinecone import ServerlessSpec

    if not client.has_index(name):
        client.create_index(
            name=name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud=cloud, region=region),
        )
    deadline = time.monotonic() + wait_seconds
    while True:
        description = client.describe_index(name)
        if description.dimension != dimension:
            raise VectorIndexError(
                f"Pinecone index {name!r} has dimension {description.dimension}, but the embedding "
                f"model produces {dimension}. Use a different index name or delete the old index."
            )
        if description.status["ready"]:
            return str(description.host)
        if time.monotonic() > deadline:
            raise VectorIndexError(
                f"Pinecone index {name!r} was not ready after {wait_seconds:.0f} s"
            )
        time.sleep(2)
