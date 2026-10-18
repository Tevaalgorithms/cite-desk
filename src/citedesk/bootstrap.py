"""Wires the concrete parts together. This is the only module that imports both
ingestion and the answer flow, so the two stay independent of each other.
"""

from dataclasses import dataclass

from citedesk.answer.rerankers import OverlapReranker
from citedesk.answer.retrieval import HybridRetriever
from citedesk.answer.service import AnswerService
from citedesk.answer.writers import ExtractiveAnswerWriter
from citedesk.config import Settings
from citedesk.domain.models import ModelHealth, ModelInfo, UsageSnapshot, searchable_text
from citedesk.domain.ports import (
    AnswerWriter,
    Embedder,
    IndexItem,
    ModelStatus,
    Reranker,
    VectorIndex,
)
from citedesk.ingestion.fetching import UrlFetcher
from citedesk.ingestion.service import IngestionService
from citedesk.storage.dev_adapters import HashingEmbedder, InMemoryVectorIndex
from citedesk.storage.repository import SqlRepository


@dataclass(frozen=True)
class App:
    ingestion: IngestionService
    answers: AnswerService
    repository: SqlRepository
    # Exposed so the evaluation code can measure each retrieval stage on its own.
    embedder: Embedder
    index: VectorIndex
    reranker: Reranker
    model: ModelStatus  # describes and checks whichever writer is in use


def build_app(settings: Settings | None = None, *, writer: AnswerWriter | None = None) -> App:
    """Build the app with the offline dev adapters.

    The in-memory vector index forgets everything when the process exits, so published
    documents are loaded back into it here. A real vector database would not need this.
    Pass `writer` to replace the default extractive answer writer.
    """
    settings = settings or Settings()
    repository = SqlRepository.from_url(settings.database_url)
    embedder, reranker = build_models(settings)
    chosen_writer = writer or build_writer(settings)
    index = InMemoryVectorIndex()
    _reload_index(repository, embedder, index)

    retriever = HybridRetriever(
        embedder,
        index,
        reranker,
        candidate_limit=settings.candidate_limit,
        rerank_pool=settings.rerank_pool,
        final_limit=settings.final_passage_limit,
    )
    return App(
        ingestion=IngestionService(
            repository,
            embedder,
            index,
            UrlFetcher(),
            chunk_max_chars=settings.chunk_max_chars,
            min_document_chars=settings.min_document_chars,
        ),
        answers=AnswerService(
            repository,
            retriever,
            chosen_writer,
            min_relevance=settings.relevance_threshold,
            max_attempts=settings.max_answer_attempts,
        ),
        repository=repository,
        embedder=embedder,
        index=index,
        reranker=reranker,
        model=_model_status(chosen_writer),
    )


RETRIEVAL_DESCRIPTIONS = {
    "local": "Embeddings: bge-small-en-v1.5. Reranker: ms-marco MiniLM. Both run locally.",
    "offline": "Embeddings and reranker: word-matching stand-ins (no models).",
}


def build_writer(settings: Settings) -> AnswerWriter:
    """The answer writer chosen by CITEDESK_WRITER."""
    if settings.writer == "openai":
        if settings.openai_api_key is None:
            raise RuntimeError("CITEDESK_WRITER=openai needs CITEDESK_OPENAI_API_KEY to be set.")
        # Imported here so the extractive writer works without calling OpenAI at all.
        from openai import OpenAI

        from citedesk.adapters.openai_writer import OpenAIAnswerWriter

        client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
            max_retries=1,
        )
        return OpenAIAnswerWriter(
            client,
            settings.openai_model,
            max_output_tokens=settings.openai_max_output_tokens,
            retrieval_description=RETRIEVAL_DESCRIPTIONS[settings.models],
        )
    return ExtractiveAnswerWriter()


class _PlainModelStatus:
    """Status for a writer that cannot describe itself (for example a test double)."""

    def info(self) -> ModelInfo:
        return ModelInfo(writer="custom", provider="custom", model="custom", description="")

    def check(self) -> ModelHealth:
        return ModelHealth(state="offline", detail="This writer does not report its status")

    def usage(self) -> UsageSnapshot | None:
        return None


def _model_status(writer: AnswerWriter) -> ModelStatus:
    return writer if isinstance(writer, ModelStatus) else _PlainModelStatus()


def build_models(settings: Settings) -> tuple[Embedder, Reranker]:
    """The embedding model and reranker for the chosen backend."""
    if settings.models == "local":
        # Imported here so the offline backend works without the optional `models` extra.
        from citedesk.adapters.local_models import CrossEncoderReranker, FastEmbedEmbedder

        return FastEmbedEmbedder(), CrossEncoderReranker()
    return HashingEmbedder(), OverlapReranker()


def _reload_index(repository: SqlRepository, embedder: Embedder, index: VectorIndex) -> None:
    passages = repository.published_passages()
    vectors = embedder.embed(
        [searchable_text(p.document_title, p.section_path, p.text) for p in passages]
    )
    index.upsert(
        [
            IndexItem(passage.chunk_id, passage.document_id, vector)
            for passage, vector in zip(passages, vectors, strict=True)
        ]
    )
