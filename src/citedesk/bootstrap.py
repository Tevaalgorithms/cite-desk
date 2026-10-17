"""Wires the concrete parts together. This is the only module that imports both
ingestion and the answer flow, so the two stay independent of each other.
"""

from dataclasses import dataclass

from citedesk.answer.rerankers import OverlapReranker
from citedesk.answer.retrieval import HybridRetriever
from citedesk.answer.service import AnswerService
from citedesk.answer.writers import ExtractiveAnswerWriter
from citedesk.config import Settings
from citedesk.domain.models import searchable_text
from citedesk.domain.ports import AnswerWriter, IndexItem
from citedesk.ingestion.fetching import UrlFetcher
from citedesk.ingestion.service import IngestionService
from citedesk.storage.dev_adapters import HashingEmbedder, InMemoryVectorIndex
from citedesk.storage.repository import SqlRepository


@dataclass(frozen=True)
class App:
    ingestion: IngestionService
    answers: AnswerService
    repository: SqlRepository


def build_app(settings: Settings | None = None, *, writer: AnswerWriter | None = None) -> App:
    """Build the app with the offline dev adapters.

    The in-memory vector index forgets everything when the process exits, so published
    documents are loaded back into it here. A real vector database would not need this.
    Pass `writer` to replace the default extractive answer writer.
    """
    settings = settings or Settings()
    repository = SqlRepository.from_url(settings.database_url)
    embedder = HashingEmbedder()
    index = InMemoryVectorIndex()
    _reload_index(repository, embedder, index)

    retriever = HybridRetriever(
        embedder,
        index,
        OverlapReranker(),
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
            writer or ExtractiveAnswerWriter(),
            min_relevance=settings.min_relevance,
            max_attempts=settings.max_answer_attempts,
        ),
        repository=repository,
    )


def _reload_index(
    repository: SqlRepository, embedder: HashingEmbedder, index: InMemoryVectorIndex
) -> None:
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
