from citedesk.evaluation.golden import GoldenCase
from citedesk.evaluation.threshold import suggest_threshold


def _case(case_id: str, answerable: bool) -> GoldenCase:
    return GoldenCase(case_id, "x", "q", answerable, ("S",) if answerable else ())


def test_a_clean_gap_between_answerable_and_unanswerable_is_separable() -> None:
    cases = [_case("a1", True), _case("a2", True), _case("u1", False)]
    result = suggest_threshold(cases, {"a1": 5.0, "a2": 2.0, "u1": -8.0})
    assert result.separable
    assert result.suggested == -3.0
    assert result.answerable_lost_above_unanswerable == 0


def test_overlapping_scores_are_reported_with_the_questions_that_would_be_lost() -> None:
    cases = [_case("a1", True), _case("a2", True), _case("u1", False)]
    result = suggest_threshold(cases, {"a1": 5.0, "a2": -9.0, "u1": -8.0})
    assert not result.separable
    assert result.answerable_lost_above_unanswerable == 1


def test_a_set_with_only_answerable_questions_cannot_calibrate_but_does_not_crash() -> None:
    result = suggest_threshold([_case("a1", True)], {"a1": 1.0})
    assert result.suggested is None
    assert result.highest_unanswerable is None
    assert not result.separable


def test_a_set_with_only_unanswerable_questions_cannot_calibrate_either() -> None:
    result = suggest_threshold([_case("u1", False)], {"u1": -9.0})
    assert result.suggested is None
    assert result.lowest_answerable is None
