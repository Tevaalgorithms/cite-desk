"""Answer questions from the published corpus."""

from citedesk.answer.flow import build_answer_flow
from citedesk.answer.retrieval import HybridRetriever, PublishedCorpus
from citedesk.domain.models import Answer, Passage
from citedesk.domain.ports import AnswerWriter, CorpusReader


class AnswerService:
    def __init__(
        self,
        corpus_reader: CorpusReader,
        retriever: HybridRetriever,
        writer: AnswerWriter,
        *,
        min_relevance: float = 0.3,
        max_attempts: int = 2,
    ) -> None:
        self._corpus_reader = corpus_reader
        self._retriever = retriever
        self._writer = writer
        self._min_relevance = min_relevance
        self._max_attempts = max_attempts
        self._cached_corpus: PublishedCorpus | None = None

    def ask(self, question: str) -> Answer:
        """Answer from published documents only, or refuse."""
        corpus = self._current_corpus()
        if not question.strip():
            return Answer(
                question=question,
                refused=True,
                refusal_reason="empty_question",
                corpus_version=corpus.version,
            )
        # A new flow per question: nothing is shared between two questions.
        flow = build_answer_flow(
            lambda text: self._retrieve(text, corpus), self._writer, max_attempts=self._max_attempts
        )
        return flow(question, corpus.version)

    def source_passage(self, chunk_id: str) -> Passage | None:
        """The passage behind a citation, for the source drawer. Published content only."""
        return self._corpus_reader.get_passage(chunk_id)

    def _current_corpus(self) -> PublishedCorpus:
        """Rebuild the keyword index only when the published corpus has changed."""
        version = self._corpus_reader.corpus_version()
        cached = self._cached_corpus
        if cached is None or cached.version != version:
            cached = PublishedCorpus.build(version, self._corpus_reader.published_passages())
            self._cached_corpus = cached
        return cached

    def _retrieve(self, question: str, corpus: PublishedCorpus) -> list[Passage]:
        passages = self._retriever.retrieve(question, corpus)
        return [passage for passage in passages if passage.score >= self._min_relevance]
