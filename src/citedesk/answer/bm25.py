"""Keyword search with the Okapi BM25 formula, held in memory."""

import math
from collections import Counter
from collections.abc import Mapping

from citedesk.text import tokenize


class Bm25Index:
    """Scores documents against a query by word overlap, favouring rare words.

    Built once from `{id: text}`; rebuilt whenever the published corpus changes.
    """

    def __init__(self, texts: Mapping[str, str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._term_counts = {doc_id: Counter(tokenize(text)) for doc_id, text in texts.items()}
        self._lengths = {doc_id: sum(c.values()) for doc_id, c in self._term_counts.items()}
        total = sum(self._lengths.values())
        self._average_length = total / len(self._lengths) if self._lengths else 0.0

        documents_with_term: Counter[str] = Counter()
        for counts in self._term_counts.values():
            documents_with_term.update(counts.keys())
        document_count = len(self._term_counts)
        self._idf = {
            term: math.log(1 + (document_count - n + 0.5) / (n + 0.5))
            for term, n in documents_with_term.items()
        }

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        """Return (id, score) for the best matches, best first. Zero scores are left out."""
        query_terms = set(tokenize(query))
        scored = [(doc_id, self._score(query_terms, doc_id)) for doc_id in self._term_counts]
        ranked = sorted((pair for pair in scored if pair[1] > 0), key=lambda p: p[1], reverse=True)
        return ranked[:limit]

    def _score(self, query_terms: set[str], doc_id: str) -> float:
        counts = self._term_counts[doc_id]
        length_ratio = self._lengths[doc_id] / self._average_length if self._average_length else 1.0
        score = 0.0
        for term in query_terms:
            frequency = counts.get(term, 0)
            if frequency == 0:
                continue
            numerator = frequency * (self._k1 + 1)
            denominator = frequency + self._k1 * (1 - self._b + self._b * length_ratio)
            score += self._idf[term] * numerator / denominator
        return score
