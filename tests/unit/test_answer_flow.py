from collections.abc import Sequence

from citedesk.bootstrap import App
from citedesk.domain.models import Passage
from tests.conftest import SECOND_DOCUMENT


def test_answers_with_a_verified_citation_to_the_right_section(published_app: App) -> None:
    answer = published_app.answers.ask("How many vacation days do I get?")

    assert not answer.refused
    assert "20 days" in answer.text
    assert answer.citations[0].section_path.endswith("Time off > Vacation")
    assert answer.citations[0].marker == 1
    assert "20 days" in answer.citations[0].quote


def test_each_question_finds_its_own_section(published_app: App) -> None:
    answer = published_app.answers.ask("When do I have to return my laptop?")
    assert "5 business days" in answer.text
    assert answer.citations[0].section_path.endswith("Returning equipment")


def test_refuses_when_nothing_relevant_is_published(published_app: App) -> None:
    answer = published_app.answers.ask("What is the capital of France?")
    assert answer.refused
    assert answer.refusal_reason == "nothing_relevant_found"
    assert answer.text == ""


def test_refuses_an_empty_question(published_app: App) -> None:
    assert published_app.answers.ask("   ").refused


def test_a_newly_published_document_is_found_without_restarting(published_app: App) -> None:
    assert published_app.answers.ask("How long must passwords be?").refused

    document = published_app.ingestion.add_text(
        SECOND_DOCUMENT,
        content_type="markdown",
        title="Security Policy",
        source_name="tests",
        actor="tester",
        license="CC0",
    )
    published_app.ingestion.publish(document.id, actor="tester")

    answer = published_app.answers.ask("How long must passwords be?")
    assert not answer.refused
    assert "14 characters" in answer.text


def test_source_passage_only_serves_published_content(published_app: App, app: App) -> None:
    answer = published_app.answers.ask("How many vacation days do I get?")
    chunk_id = answer.citations[0].chunk_id
    assert published_app.answers.source_passage(chunk_id) is not None
    assert published_app.answers.source_passage("missing") is None


class _RecordingWriter:
    """A writer that never cites anything, to prove the verifier blocks bad drafts."""

    def __init__(self) -> None:
        self.strict_flags: list[bool] = []

    def write(self, question: str, passages: Sequence[Passage], *, strict: bool) -> str:
        self.strict_flags.append(strict)
        return "Employees get lots of vacation."


def test_an_unverifiable_draft_is_retried_once_then_refused(make_app) -> None:  # type: ignore[no-untyped-def]
    writer = _RecordingWriter()
    app = make_app(writer)
    document = app.ingestion.add_text(
        "# Handbook\n\n## Vacation\n\nFull-time employees receive 20 days of paid vacation each year. "
        "Unused days carry over for up to 5 days.",
        content_type="markdown",
        title="Handbook",
        source_name="tests",
        actor="tester",
        license="CC0",
    )
    app.ingestion.publish(document.id, actor="tester")

    answer = app.answers.ask("How many vacation days do I get?")

    assert answer.refused
    assert answer.refusal_reason == "could_not_verify_answer"
    assert writer.strict_flags == [False, True]  # second attempt asks for the strict style


def test_a_strong_match_is_not_padded_with_weaker_passages(published_app: App) -> None:
    # "5 business days" mentions "days" too, but it is a weaker match for a vacation question.
    answer = published_app.answers.ask("How many vacation days do I get?")
    assert len(answer.citations) == 1
    assert "laptop" not in answer.text


def test_citation_paths_do_not_repeat_the_document_title(published_app: App) -> None:
    answer = published_app.answers.ask("How many vacation days do I get?")
    assert answer.citations[0].section_path == "Time off > Vacation"
