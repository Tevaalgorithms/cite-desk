from citedesk.answer.verifier import cited_markers, verify_answer
from citedesk.domain.models import Passage

PASSAGES = [
    Passage(
        chunk_id="c1",
        document_id="d1",
        document_title="Handbook",
        section_path="Time off > Vacation",
        text='Full-time employees receive 20 days of paid vacation each year. The policy says "carry over up to 5 days".',
    ),
    Passage(
        chunk_id="c2",
        document_id="d1",
        document_title="Handbook",
        section_path="Equipment",
        text="Return your laptop within 5 business days.",
    ),
]


def test_a_supported_cited_answer_passes() -> None:
    result = verify_answer(
        "Full-time employees receive 20 days of paid vacation each year [1]. "
        "Return your laptop within 5 business days [2].",
        PASSAGES,
    )
    assert result.passed, result.problems


def test_a_sentence_without_a_citation_fails() -> None:
    result = verify_answer("Employees receive 20 days of paid vacation.", PASSAGES)
    assert not result.passed
    assert "No citation" in result.problems[0]


def test_an_unknown_marker_fails() -> None:
    result = verify_answer("Employees receive paid vacation [9].", PASSAGES)
    assert not result.passed
    assert "Unknown citation" in result.problems[0]


def test_a_number_missing_from_the_cited_passage_fails() -> None:
    result = verify_answer("Full-time employees receive 25 days of paid vacation [1].", PASSAGES)
    assert not result.passed
    assert "25" in result.problems[0]


def test_a_quote_must_appear_word_for_word() -> None:
    good = verify_answer('The policy says "carry over up to 5 days" [1].', PASSAGES)
    bad = verify_answer('The policy says "carry over up to 9 weeks" [1].', PASSAGES)
    assert good.passed, good.problems
    assert not bad.passed


def test_unsupported_wording_fails_even_with_a_marker() -> None:
    result = verify_answer(
        "Employees may bring pets and receive free lunches every Friday [1].", PASSAGES
    )
    assert not result.passed
    assert "supported" in result.problems[0]


def test_an_empty_answer_fails() -> None:
    assert not verify_answer("", PASSAGES).passed


def test_cited_markers_are_listed_once_in_order() -> None:
    assert cited_markers("A [2]. B [1] [2]. C [1].") == [2, 1]
