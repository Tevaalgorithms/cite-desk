"""Rerankers: order candidate passages by how well they answer the question."""

from collections.abc import Sequence

from citedesk.domain.models import Passage
from citedesk.text import content_tokens


class OverlapReranker:
    """Dev stand-in for the cross-encoder: scores a passage by how many of the
    question's content words it contains (0..1). Replace with a real cross-encoder
    (next ticket) before judging answer quality.
    """

    def rerank(self, question: str, passages: Sequence[Passage]) -> list[Passage]:
        wanted = set(content_tokens(question))
        if not wanted:
            return []
        rescored = [
            passage.model_copy(
                update={"score": len(wanted & set(content_tokens(passage.text))) / len(wanted)}
            )
            for passage in passages
        ]
        return sorted(rescored, key=lambda p: p.score, reverse=True)
