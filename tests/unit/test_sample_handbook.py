"""The sample handbook and its questions double as a small end-to-end regression suite."""

import json
from pathlib import Path

import pytest

from citedesk.bootstrap import App

ROOT = Path(__file__).resolve().parents[2]
HANDBOOK = ROOT / "data" / "sample" / "acme-handbook.md"
QUESTIONS = json.loads((ROOT / "evals" / "sample" / "questions.json").read_text())


@pytest.fixture
def sample_app(app: App) -> App:
    document = app.ingestion.add_text(
        HANDBOOK.read_text(),
        content_type="markdown",
        title="Acme Robotics Employee Handbook",
        source_name="sample data",
        actor="tester",
        license="CC0 (synthetic sample)",
    )
    app.ingestion.publish(document.id, actor="tester")
    return app


@pytest.mark.parametrize("case", QUESTIONS, ids=[case["id"] for case in QUESTIONS])
def test_sample_questions(sample_app: App, case: dict[str, object]) -> None:
    answer = sample_app.answers.ask(str(case["question"]))

    if not case["answerable"]:
        assert answer.refused, answer.text
        return

    assert not answer.refused, f"refused: {answer.refusal_reason}"
    assert str(case["expected_text"]) in answer.text
    assert answer.citations[0].section_path == case["expected_section"]


@pytest.mark.parametrize(
    ("question", "right_section"),
    [
        ("How much time off do I get when I have a baby?", "Time off > Parental leave"),
        ("How many holidays does the company observe?", "Time off > Public holidays"),
    ],
)
def test_rephrased_questions_are_refused_never_answered_from_the_wrong_section(
    sample_app: App, question: str, right_section: str
) -> None:
    """The word-matching stand-ins cannot handle rephrasing. They must say so, not guess."""
    answer = sample_app.answers.ask(question)
    assert answer.refused or answer.citations[0].section_path == right_section
    assert all(c.section_path == right_section for c in answer.citations)
