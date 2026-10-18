"""Keep a vector index equal to what the database says is published.

The database is the source of truth. An index can lose vectors (restart of an in-memory index,
a failed write) or keep stale ones (a delete that did not finish). `sync_vector_index` repairs
either by adding what is missing and removing what is extra, so it is safe to run at every start.
"""

import logging
from dataclasses import dataclass

from citedesk.domain.models import Passage, searchable_text
from citedesk.domain.ports import CorpusReader, Embedder, IndexItem, VectorIndex

logger = logging.getLogger("citedesk.indexing")
_EMBED_BATCH = 64


@dataclass(frozen=True)
class SyncReport:
    published: int  # chunks that should be in the index
    added: int
    removed: int


def sync_vector_index(corpus: CorpusReader, embedder: Embedder, index: VectorIndex) -> SyncReport:
    passages = corpus.published_passages()
    wanted = {passage.chunk_id for passage in passages}
    present = index.ids()

    missing = [passage for passage in passages if passage.chunk_id not in present]
    _add(missing, embedder, index)
    extra = sorted(present - wanted)
    if extra:
        index.delete_ids(extra)

    report = SyncReport(published=len(wanted), added=len(missing), removed=len(extra))
    if report.added or report.removed:
        logger.warning(
            "Vector index repaired: %d added, %d removed (%d published)",
            report.added, report.removed, report.published,
        )  # fmt: skip
    return report


def _add(passages: list[Passage], embedder: Embedder, index: VectorIndex) -> None:
    for start in range(0, len(passages), _EMBED_BATCH):
        batch = passages[start : start + _EMBED_BATCH]
        vectors = embedder.embed(
            [searchable_text(p.document_title, p.section_path, p.text) for p in batch]
        )
        index.upsert(
            [
                IndexItem(passage.chunk_id, passage.document_id, vector)
                for passage, vector in zip(batch, vectors, strict=True)
            ]
        )
