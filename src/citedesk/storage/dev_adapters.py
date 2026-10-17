"""Offline stand-ins for the vector database and the embedding model.

They let the whole system run and be tested without API keys. They are NOT meant for
real quality: replace them with the Pinecone index and a real embedding model
(next ticket) before judging retrieval quality.
"""

import hashlib
import math
from collections.abc import Sequence

from citedesk.domain.ports import IndexItem
from citedesk.text import content_tokens


class HashingEmbedder:
    """Turns text into a fixed-size vector by hashing its words into buckets.

    Texts that share words get similar vectors. It has no understanding of meaning,
    so "quit" will not match "resignation"; a real model will.
    """

    def __init__(self, dimension: int = 256) -> None:
        self._dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for token in content_tokens(text):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        length = math.sqrt(sum(value * value for value in vector))
        return [value / length for value in vector] if length else vector


class InMemoryVectorIndex:
    """A dictionary of vectors searched by cosine similarity. Lost when the process exits."""

    def __init__(self) -> None:
        self._items: dict[str, IndexItem] = {}

    def upsert(self, items: Sequence[IndexItem]) -> None:
        for item in items:
            self._items[item.chunk_id] = item

    def delete_document(self, document_id: str) -> None:
        self._items = {
            chunk_id: item
            for chunk_id, item in self._items.items()
            if item.document_id != document_id
        }

    def search(self, vector: Sequence[float], limit: int) -> list[tuple[str, float]]:
        scored = [
            (item.chunk_id, sum(a * b for a, b in zip(vector, item.vector, strict=True)))
            for item in self._items.values()
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [pair for pair in scored[:limit] if pair[1] > 0]
