"""Pick the relevance threshold from data instead of guessing it."""

from dataclasses import dataclass

from citedesk.evaluation.golden import GoldenCase


@dataclass(frozen=True)
class ThresholdSuggestion:
    # The scores are None when the question set has no questions of that kind, because a
    # threshold cannot be calibrated from one side alone.
    separable: bool  # True if every answerable top score is above every unanswerable one
    lowest_answerable: float | None
    highest_unanswerable: float | None
    suggested: float | None  # midpoint of the two
    answerable_lost_above_unanswerable: int  # answerable questions scoring no higher than the
    # strongest unanswerable one: they would be refused by a threshold that refuses every known
    # unanswerable question


def suggest_threshold(cases: list[GoldenCase], top_scores: dict[str, float]) -> ThresholdSuggestion:
    """Suggest a threshold between the weakest answerable score and the strongest unanswerable one.

    If the two ranges overlap no threshold is perfect, and the suggestion is the midpoint of the
    overlap. Re-run after changing the models, the handbook or the questions.
    """
    answerable = [top_scores[c.id] for c in cases if c.answerable]
    unanswerable = [top_scores[c.id] for c in cases if not c.answerable]
    lowest = min(answerable) if answerable else None
    highest = max(unanswerable) if unanswerable else None
    if lowest is None or highest is None:
        return ThresholdSuggestion(
            separable=False,
            lowest_answerable=lowest,
            highest_unanswerable=highest,
            suggested=None,
            answerable_lost_above_unanswerable=0,
        )
    return ThresholdSuggestion(
        separable=lowest > highest,
        lowest_answerable=lowest,
        highest_unanswerable=highest,
        suggested=(lowest + highest) / 2,
        answerable_lost_above_unanswerable=sum(1 for score in answerable if score <= highest),
    )
