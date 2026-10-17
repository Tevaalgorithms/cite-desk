"""Measure how well each retrieval stage finds the right section.

Stages, from simplest to the full pipeline: keyword only, vector only, both fused, and
fused + reranked. Comparing them shows what each stage adds (an "ablation").
"""

from dataclasses import dataclass, field

from citedesk.answer.fusion import reciprocal_rank_fusion
from citedesk.answer.retrieval import PublishedCorpus
from citedesk.bootstrap import App
from citedesk.domain.models import Passage
from citedesk.evaluation.golden import GoldenCase

STAGES = ("keyword", "vector", "hybrid", "hybrid_rerank")
_CANDIDATES = 20
_POOL = 30
_MRR_DEPTH = 10


@dataclass(frozen=True)
class StageMetrics:
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float


@dataclass(frozen=True)
class RetrievalReport:
    # stage -> category -> metrics ("all" covers every answerable question)
    stages: dict[str, dict[str, StageMetrics]]
    # Reranker score of the best passage for each question, by question id (full pipeline)
    top_scores: dict[str, float]
    questions: int
    unanswerable_ids: list[str] = field(default_factory=list)


def evaluate_retrieval(app: App, cases: list[GoldenCase]) -> RetrievalReport:
    """Run every golden question through every stage. The app must have published documents."""
    corpus = PublishedCorpus.build(
        app.repository.corpus_version(), app.repository.published_passages()
    )
    _check_gold_sections_exist(corpus, cases)

    answerable = [case for case in cases if case.answerable]
    stages: dict[str, dict[str, StageMetrics]] = {}
    top_scores: dict[str, float] = {}

    for stage in STAGES:
        ranked_by_case = {case.id: _rank(app, corpus, case.question, stage) for case in cases}
        stages[stage] = {
            "all": _metrics(answerable, ranked_by_case),
            **{
                category: _metrics(
                    [c for c in answerable if c.category == category], ranked_by_case
                )
                for category in sorted({c.category for c in answerable})
            },
        }
        if stage == "hybrid_rerank":
            top_scores = {
                case.id: (ranked_by_case[case.id][0].score if ranked_by_case[case.id] else 0.0)
                for case in cases
            }

    return RetrievalReport(
        stages=stages,
        top_scores=top_scores,
        questions=len(cases),
        unanswerable_ids=[case.id for case in cases if not case.answerable],
    )


def _rank(app: App, corpus: PublishedCorpus, question: str, stage: str) -> list[Passage]:
    keyword_ids = [i for i, _ in corpus.keyword_index.search(question, _CANDIDATES)]
    vector_ids = [
        i
        for i, _ in app.index.search(app.embedder.embed_query(question), _CANDIDATES)
        if i in corpus.passages
    ]
    if stage == "keyword":
        ids = keyword_ids
    elif stage == "vector":
        ids = vector_ids
    else:
        ids = [i for i, _ in reciprocal_rank_fusion([keyword_ids, vector_ids])[:_POOL]]
    passages = [corpus.passages[i] for i in ids]
    return app.reranker.rerank(question, passages) if stage == "hybrid_rerank" else passages


def _metrics(cases: list[GoldenCase], ranked_by_case: dict[str, list[Passage]]) -> StageMetrics:
    if not cases:
        return StageMetrics(0.0, 0.0, 0.0, 0.0)

    def first_hit(case: GoldenCase) -> int | None:
        for position, passage in enumerate(ranked_by_case[case.id][:_MRR_DEPTH], start=1):
            if passage.section_path in case.gold_sections:
                return position
        return None

    positions = [first_hit(case) for case in cases]
    total = len(cases)

    def recall(k: int) -> float:
        return sum(1 for p in positions if p is not None and p <= k) / total

    return StageMetrics(
        recall_at_1=recall(1),
        recall_at_3=recall(3),
        recall_at_5=recall(5),
        mrr=sum(1 / p for p in positions if p is not None) / total,
    )


def _check_gold_sections_exist(corpus: PublishedCorpus, cases: list[GoldenCase]) -> None:
    known = {passage.section_path for passage in corpus.passages.values()}
    for case in cases:
        missing = [s for s in case.gold_sections if s not in known]
        if missing:
            raise ValueError(f"{case.id}: gold section(s) not in the corpus: {missing}")
