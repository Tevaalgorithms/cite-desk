"""Real embedding model and cross-encoder that run on this machine (ONNX, no API key).

Needs the optional `models` extra (`uv sync --extra models`). Model files are downloaded
the first time they are used and cached afterwards.
"""

from collections.abc import Sequence

from citedesk.domain.models import Passage, searchable_text


class FastEmbedEmbedder:
    """BAAI/bge-small-en-v1.5: a small sentence-embedding model (384 numbers per text)."""

    model_id = "BAAI/bge-small-en-v1.5"
    dimension = 384

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(self.model_id)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(x) for x in vector] for vector in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        # fastembed adds the model's recommended question prompt for queries.
        return [float(x) for x in next(iter(self._model.query_embed([text])))]


class CrossEncoderReranker:
    """ms-marco MiniLM cross-encoder: reads the question and a passage together.

    Scores are the model's raw output: unbounded, higher is more relevant, and typically
    between about -12 and +8. They are NOT probabilities, so the relevance threshold must be
    calibrated with `citedesk eval-retrieval` and never copied from another model.
    """

    model_id = "Xenova/ms-marco-MiniLM-L-6-v2"

    def __init__(self) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(self.model_id)

    def rerank(self, question: str, passages: Sequence[Passage]) -> list[Passage]:
        if not passages:
            return []
        texts = [searchable_text(p.document_title, p.section_path, p.text) for p in passages]
        logits = [float(score) for score in self._model.rerank(question, texts)]
        rescored = [
            passage.model_copy(update={"score": logit})
            for passage, logit in zip(passages, logits, strict=True)
        ]
        return sorted(rescored, key=lambda p: p.score, reverse=True)
