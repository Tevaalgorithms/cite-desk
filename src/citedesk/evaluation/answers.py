"""Measure whole answers: right section cited, refused when it should be, never wrong."""

from dataclasses import dataclass

from citedesk.bootstrap import App
from citedesk.evaluation.golden import GoldenCase


@dataclass(frozen=True)
class AnswerReport:
    correct: int  # answerable, answered, every citation in a gold section
    wrongly_refused: int  # answerable but refused (safe, but unhelpful)
    wrong_section: int  # answered, but cited something outside the gold sections (worst case)
    unanswerable_refused: int  # correctly refused
    unanswerable_answered: int  # answered although the handbook has no answer (bad)
    answerable_total: int
    unanswerable_total: int
    problems: tuple[str, ...]  # one line per failure, for reading

    @property
    def correct_rate(self) -> float:
        return self.correct / self.answerable_total if self.answerable_total else 0.0

    @property
    def refusal_rate(self) -> float:
        return (
            self.unanswerable_refused / self.unanswerable_total if self.unanswerable_total else 1.0
        )

    @property
    def confidently_wrong(self) -> int:
        return self.wrong_section + self.unanswerable_answered


def evaluate_answers(app: App, cases: list[GoldenCase]) -> AnswerReport:
    correct = wrongly_refused = wrong_section = refused_ok = answered_bad = 0
    problems: list[str] = []

    for case in cases:
        answer = app.answers.ask(case.question)
        cited = {citation.section_path for citation in answer.citations}

        if case.answerable:
            if answer.refused:
                wrongly_refused += 1
                problems.append(f"{case.id} refused ({answer.refusal_reason}): {case.question}")
            elif cited <= set(case.gold_sections):
                correct += 1
            else:
                wrong_section += 1
                problems.append(f"{case.id} cited {sorted(cited)}: {case.question}")
        elif answer.refused:
            refused_ok += 1
        else:
            answered_bad += 1
            problems.append(f"{case.id} answered an unanswerable question: {case.question}")

    answerable_total = sum(1 for case in cases if case.answerable)
    return AnswerReport(
        correct=correct,
        wrongly_refused=wrongly_refused,
        wrong_section=wrong_section,
        unanswerable_refused=refused_ok,
        unanswerable_answered=answered_bad,
        answerable_total=answerable_total,
        unanswerable_total=len(cases) - answerable_total,
        problems=tuple(problems),
    )
