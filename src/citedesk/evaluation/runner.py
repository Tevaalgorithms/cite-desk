"""Build a throwaway app on the sample handbook and print the evaluation tables."""

import tempfile
from pathlib import Path

from citedesk.bootstrap import App, build_app
from citedesk.config import ModelBackend, Settings
from citedesk.evaluation.answers import AnswerReport, evaluate_answers
from citedesk.evaluation.golden import GoldenCase, load_golden_cases
from citedesk.evaluation.retrieval import STAGES, RetrievalReport, evaluate_retrieval
from citedesk.evaluation.threshold import ThresholdSuggestion, suggest_threshold


def build_sample_app(models: ModelBackend, handbook: Path, database_dir: Path) -> App:
    settings = Settings(database_url=f"sqlite:///{database_dir / 'eval.db'}", models=models)
    app = build_app(settings)
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


def run_evaluation(
    models: ModelBackend, handbook: Path, golden: Path
) -> tuple[RetrievalReport, ThresholdSuggestion, AnswerReport, float, list[GoldenCase]]:
    cases = load_golden_cases(golden)
    with tempfile.TemporaryDirectory() as folder:
        app = build_sample_app(models, handbook, Path(folder))
        retrieval = evaluate_retrieval(app, cases)
        answers = evaluate_answers(app, cases)
    threshold = Settings(models=models).relevance_threshold
    return retrieval, suggest_threshold(cases, retrieval.top_scores), answers, threshold, cases


def format_report(
    models: ModelBackend,
    retrieval: RetrievalReport,
    suggestion: ThresholdSuggestion,
    answers: AnswerReport,
    threshold: float,
) -> str:
    lines = [f"Backend: {models}   questions: {retrieval.questions}", ""]
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
        f"  lowest answerable top score : {suggestion.lowest_answerable:.3f}",
        f"  highest unanswerable score  : {suggestion.highest_unanswerable:.3f}",
        f"  separable                   : {_yes_no(suggestion.separable)}",
        f"  midpoint                    : {suggestion.suggested:.3f}   (in use: {threshold})",
        f"  answerable at or below the strongest unanswerable score: "
        f"{suggestion.answerable_lost_above_unanswerable} (a threshold above it refuses these)",
        "",
        f"Answers at threshold {threshold}",
        f"  correct (right section cited)      : {answers.correct}/{answers.answerable_total}",
        f"  refused although answerable        : {answers.wrongly_refused}",
        f"  cited the wrong section            : {answers.wrong_section}",
        f"  unanswerable correctly refused     : "
        f"{answers.unanswerable_refused}/{answers.unanswerable_total}",
        f"  unanswerable answered anyway       : {answers.unanswerable_answered}",
    ]
    lines += [f"    - {problem}" for problem in answers.problems]
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "NO (ranges overlap)"


def summarize(retrieval: RetrievalReport, answers: AnswerReport) -> dict[str, float]:
    """The numbers the quality gates compare against `evals/baselines.json`."""
    final = retrieval.stages["hybrid_rerank"]["all"]
    return {
        "recall_at_1": round(final.recall_at_1, 4),
        "recall_at_3": round(final.recall_at_3, 4),
        "recall_at_5": round(final.recall_at_5, 4),
        "mrr": round(final.mrr, 4),
        "correct": answers.correct,
        "confidently_wrong": answers.confidently_wrong,
        "unanswerable_answered": answers.unanswerable_answered,
    }
