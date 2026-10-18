"""For multi-part questions: does retrieval hand the writer every section the answer needs?

This is the test of whether an "agent" (splitting a question into several searches) would help. An
agent can only improve results when retrieval misses a needed section. If coverage is complete, the
remaining errors are the writer's, and more searching cannot fix them.
"""

from dataclasses import dataclass

from citedesk.bootstrap import App
from citedesk.evaluation.golden import GoldenCase


@dataclass(frozen=True)
class CoverageReport:
    questions: int
    complete: int  # questions whose passages include every needed section
    gaps: tuple[str, ...]  # one line per question that is missing a section


def evaluate_coverage(app: App, cases: list[GoldenCase]) -> CoverageReport | None:
    """None when there are no multi-part questions to check."""
    multipart = [case for case in cases if case.category == "multistep"]
    if not multipart:
        return None
    complete = 0
    gaps: list[str] = []
    for case in multipart:
        reached = {passage.section_path for passage in app.answers.passages_for(case.question)}
        missing = [section for section in case.gold_sections if section not in reached]
        if missing:
            gaps.append(f"{case.id} is missing {missing}: {case.question}")
        else:
            complete += 1
    return CoverageReport(questions=len(multipart), complete=complete, gaps=tuple(gaps))
