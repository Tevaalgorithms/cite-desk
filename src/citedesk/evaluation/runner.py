"""Build a throwaway app on the sample handbook and print the evaluation tables."""

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from citedesk.bootstrap import App, build_app
from citedesk.config import ModelBackend, Settings
from citedesk.domain.models import ModelInfo, UsageSnapshot
from citedesk.evaluation.answers import AnswerReport, evaluate_answers
from citedesk.evaluation.coverage import CoverageReport, evaluate_coverage
from citedesk.evaluation.golden import GoldenCase, load_golden_cases
from citedesk.evaluation.retrieval import STAGES, RetrievalReport, evaluate_retrieval
from citedesk.evaluation.threshold import ThresholdSuggestion, suggest_threshold


def build_sample_app(
    models: ModelBackend, handbook: Path, database_dir: Path, **settings: Any
) -> App:
    """An app on a throwaway database with the sample handbook published.

    An evaluation must never touch real services or depend on a developer's local `.env`. So the
    database, vector index, cache and tracing are fixed here (a throwaway SQLite file, in-memory
    vectors, no cache, no tracing) and the answer writer defaults to the free built-in one. Pass
    `writer="openai"` explicitly to test the language model.
    """
    fixed: dict[str, Any] = {
        "database_url": f"sqlite:///{database_dir / 'eval.db'}",
        "models": models,
        "vector_index": "memory",  # never the real Pinecone index: sync would delete its vectors
        "langsmith_tracing": False,
        "answer_cache_size": 0,
        "writer": "extractive",
    }
    app = build_app(Settings(**{**fixed, **settings}))
    document = app.ingestion.add_text(
        handbook.read_text(encoding="utf-8"),
        content_type="markdown",
        title=handbook.stem,
        source_name="evaluation sample",
        actor="evaluation",
        license="CC0 (synthetic sample)",
    )
    app.ingestion.publish(document.id, actor="evaluation")
    return app


@dataclass(frozen=True)
class EvaluationRun:
    retrieval: RetrievalReport
    suggestion: ThresholdSuggestion
    answers: AnswerReport
    threshold: float
    cases: list[GoldenCase]
    model: ModelInfo
    usage: UsageSnapshot | None  # model calls and tokens spent by the answer step
    answer_seconds: float  # wall-clock time to answer every question
    coverage: CoverageReport | None  # only for sets with multi-part questions


def run_evaluation(
    models: ModelBackend, handbook: Path, golden: Path, **settings: Any
) -> EvaluationRun:
    cases = load_golden_cases(golden)
    with tempfile.TemporaryDirectory() as folder:
        app = build_sample_app(models, handbook, Path(folder), **settings)
        retrieval = evaluate_retrieval(app, cases)
        coverage = evaluate_coverage(app, cases)
        started = time.monotonic()
        answers = evaluate_answers(app, cases)
        answer_seconds = time.monotonic() - started
        model, usage = app.model.info(), app.model.usage()
    return EvaluationRun(
        retrieval=retrieval,
        suggestion=suggest_threshold(cases, retrieval.top_scores),
        answers=answers,
        threshold=Settings(models=models).relevance_threshold,
        cases=cases,
        model=model,
        usage=usage,
        answer_seconds=answer_seconds,
        coverage=coverage,
    )


def format_report(models: ModelBackend, run: EvaluationRun) -> str:
    retrieval, suggestion = run.retrieval, run.suggestion
    answers, threshold = run.answers, run.threshold
    lines = [
        f"Backend: {models}   questions: {retrieval.questions}",
        f"Answer writer: {run.model.provider} / {run.model.model}",
        "",
    ]
    lines.append("Retrieval: did the right section appear? (answerable questions)")
    lines.append(f"{'stage':<15}{'group':<14}{'R@1':>6}{'R@3':>6}{'R@5':>6}{'MRR':>7}")
    for stage in STAGES:
        for group, m in retrieval.stages[stage].items():
            lines.append(
                f"{stage:<15}{group:<14}{m.recall_at_1:>6.2f}{m.recall_at_3:>6.2f}"
                f"{m.recall_at_5:>6.2f}{m.mrr:>7.2f}"
            )
    lines += [
        "",
        "Relevance threshold",
        *_threshold_lines(suggestion, threshold),
        "",
        f"Answers at threshold {threshold}",
        f"  correct (right section cited)      : {answers.correct}/{answers.answerable_total}",
        f"  refused although answerable        : {answers.wrongly_refused}",
        f"  cited the wrong section            : {answers.wrong_section}",
        f"  incomplete (multi-part, some missed): {answers.incomplete}",
        f"  unanswerable correctly refused     : "
        f"{answers.unanswerable_refused}/{answers.unanswerable_total}",
        f"  unanswerable answered anyway       : {answers.unanswerable_answered}",
    ]
    lines += [f"    - {problem}" for problem in answers.problems]
    if run.coverage is not None:
        lines += [
            "",
            "Multi-part questions: did retrieval hand the writer every needed section?",
            f"  complete: {run.coverage.complete}/{run.coverage.questions}",
            *[f"    - {gap}" for gap in run.coverage.gaps],
        ]
    if run.usage is not None:
        calls = run.usage.calls or 1
        lines += [
            "",
            f"Model usage: {run.usage.calls} calls in {run.answer_seconds:.1f} s",
            f"  prompt tokens      : {run.usage.prompt_tokens} "
            f"({run.usage.prompt_tokens // calls} per call)",
            f"  completion tokens  : {run.usage.completion_tokens} "
            f"({run.usage.completion_tokens // calls} per call)",
        ]
    return "\n".join(lines)


def _threshold_lines(suggestion: ThresholdSuggestion, threshold: float) -> list[str]:
    if suggestion.suggested is None:
        return ["  (needs both answerable and unanswerable questions to calibrate)"]
    assert suggestion.lowest_answerable is not None
    assert suggestion.highest_unanswerable is not None
    return [
        f"  lowest answerable top score : {suggestion.lowest_answerable:.3f}",
        f"  highest unanswerable score  : {suggestion.highest_unanswerable:.3f}",
        f"  separable                   : {_yes_no(suggestion.separable)}",
        f"  midpoint                    : {suggestion.suggested:.3f}   (in use: {threshold})",
        "  answerable at or below the strongest unanswerable score: "
        f"{suggestion.answerable_lost_above_unanswerable} (a threshold above it refuses these)",
    ]


def _yes_no(value: bool) -> str:
    return "yes" if value else "NO (ranges overlap)"


def summarize(
    retrieval: RetrievalReport, answers: AnswerReport, coverage: CoverageReport | None = None
) -> dict[str, float]:
    """The numbers the quality gates compare against `evals/baselines.json`."""
    final = retrieval.stages["hybrid_rerank"]["all"]
    summary: dict[str, float] = {
        "recall_at_1": round(final.recall_at_1, 4),
        "recall_at_3": round(final.recall_at_3, 4),
        "recall_at_5": round(final.recall_at_5, 4),
        "mrr": round(final.mrr, 4),
        "correct": answers.correct,
        "confidently_wrong": answers.confidently_wrong,
        "unanswerable_answered": answers.unanswerable_answered,
    }
    if coverage is not None:
        summary["coverage_complete"] = coverage.complete
    return summary
