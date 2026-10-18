"""Hybrid retrieval: keyword + vector search, fused, then reranked."""

from collections.abc import Sequence
from dataclasses import dataclass

from citedesk.answer.bm25 import Bm25Index
from citedesk.answer.fusion import reciprocal_rank_fusion
from citedesk.domain.models import Passage, searchable_text
from citedesk.domain.ports import Embedder, Reranker, VectorIndex


@dataclass(frozen=True)
class PublishedCorpus:
    """Everything searchable at one corpus version."""

    version: int
    passages: dict[str, Passage]  # by chunk id
    keyword_index: Bm25Index

    @classmethod
    def build(cls, version: int, passages: Sequence[Passage]) -> "PublishedCorpus":
        by_id = {passage.chunk_id: passage for passage in passages}
        keyword_index = Bm25Index(
            {
                p.chunk_id: searchable_text(p.document_title, p.section_path, p.text)
                for p in passages
            }
        )
        return cls(version=version, passages=by_id, keyword_index=keyword_index)


class HybridRetriever:
    def __init__(
        self,
        embedder: Embedder,
        index: VectorIndex,
        reranker: Reranker,
        *,
        candidate_limit: int = 20,
        rerank_pool: int = 30,
        final_limit: int = 6,
    ) -> None:
        self._embedder = embedder
        self._index = index
        self._reranker = reranker
        self._candidate_limit = candidate_limit
        self._rerank_pool = rerank_pool
        self._final_limit = final_limit

    def retrieve(self, question: str, corpus: PublishedCorpus) -> list[Passage]:
        """Return the best passages for a question, best first."""
        keyword_ids = [
            chunk_id for chunk_id, _ in corpus.keyword_index.search(question, self._candidate_limit)
        ]
        question_vector = self._embedder.embed_query(question)
        vector_ids = [
            chunk_id
            for chunk_id, _ in self._index.search(question_vector, self._candidate_limit)
            if chunk_id in corpus.passages  # ignore vectors of content no longer published
        ]

        fused = reciprocal_rank_fusion([keyword_ids, vector_ids])[: self._rerank_pool]
        candidates = [corpus.passages[chunk_id] for chunk_id, _ in fused]
        return self._reranker.rerank(question, candidates)[: self._final_limit]
