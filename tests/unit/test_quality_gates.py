"""Quality gates on the offline backend: a change that makes answers worse fails the build."""

import json
from pathlib import Path

import pytest

from citedesk.cli import main
from citedesk.evaluation.gates import check_gates, load_baseline

ROOT = Path(__file__).resolve().parents[2]
BASELINES = ROOT / "evals" / "baselines.json"
BETTER = {
    "recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0, "mrr": 1.0,
    "correct": 99, "confidently_wrong": 0, "unanswerable_answered": 0,
}  # fmt: skip


@pytest.mark.parametrize("question_set", ["golden", "heldout"])
def test_offline_backend_meets_its_baseline(
    question_set: str, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "eval-retrieval", "--models", "offline",
            "--golden", str(ROOT / "evals" / "sample" / f"{question_set}.json"),
            "--handbook", str(ROOT / "data" / "sample" / "acme-handbook.md"),
            "--check", str(BASELINES),
        ]
    )  # fmt: skip
    output = capsys.readouterr()
    assert exit_code == 0, output.err
    assert "Quality gates: passed" in output.out


def test_a_worse_result_is_reported() -> None:
    baseline = load_baseline(BASELINES, "offline", "golden")
    worse = {**baseline, "recall_at_5": baseline["recall_at_5"] - 0.2, "confidently_wrong": 5}
    failures = check_gates(worse, baseline)
    assert any("recall_at_5" in failure for failure in failures)
    assert any("confidently_wrong" in failure for failure in failures)


def test_an_equal_or_better_result_passes() -> None:
    baseline = load_baseline(BASELINES, "offline", "golden")
    assert check_gates(baseline, baseline) == []
    assert check_gates(BETTER, baseline) == []


def test_unknown_baselines_raise_a_clear_error() -> None:
    with pytest.raises(KeyError, match="No baseline"):
        load_baseline(BASELINES, "offline", "does-not-exist")


def test_baselines_file_is_valid_json_with_both_backends() -> None:
    data = json.loads(BASELINES.read_text())
    assert {"offline", "local"} <= set(data)
