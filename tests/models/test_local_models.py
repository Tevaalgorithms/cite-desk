"""Tests that need the real local models. Skipped unless `uv sync --extra models` was run.

Run them with:  uv run --extra models pytest tests/models
"""

from pathlib import Path

import pytest

pytest.importorskip("fastembed")

from citedesk.cli import main
from citedesk.domain.models import Passage

pytestmark = pytest.mark.models

ROOT = Path(__file__).resolve().parents[2]


def test_embedder_returns_384_numbers_for_passages_and_questions() -> None:
    from citedesk.adapters.local_models import FastEmbedEmbedder

    embedder = FastEmbedEmbedder()
    assert len(embedder.embed(["paid parental leave"])[0]) == 384
    assert len(embedder.embed_query("how long is parental leave?")) == 384


def test_cross_encoder_ranks_the_relevant_passage_first() -> None:
    from citedesk.adapters.local_models import CrossEncoderReranker

    def passage(text: str) -> Passage:
        return Passage(
            chunk_id=text, document_id="d", document_title="T", section_path="S", text=text
        )

    ranked = CrossEncoderReranker().rerank(
        "How much time off do I get when I have a baby?",
        [
            passage("Passwords must be at least 14 characters long."),
            passage("New parents receive 16 weeks of paid parental leave."),
        ],
    )
    assert ranked[0].text.startswith("New parents")
    assert ranked[0].score > ranked[1].score


@pytest.mark.parametrize("question_set", ["golden", "heldout", "multistep"])
def test_local_backend_meets_its_baseline(
    question_set: str, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "eval-retrieval", "--models", "local",
            "--golden", str(ROOT / "evals" / "sample" / f"{question_set}.json"),
            "--handbook", str(ROOT / "data" / "sample" / "acme-handbook.md"),
            "--check", str(ROOT / "evals" / "baselines.json"),
        ]
    )  # fmt: skip
    assert exit_code == 0, capsys.readouterr().err
