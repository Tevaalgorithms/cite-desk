"""Quality gates: compare a run with the recorded baseline and list what got worse."""

import json
from pathlib import Path

# Metrics where a bigger number is better. For the rest, a smaller number is better.
_HIGHER_IS_BETTER = ("recall_at_1", "recall_at_3", "recall_at_5", "mrr", "correct")
_LOWER_IS_BETTER = ("confidently_wrong", "unanswerable_answered")
_TOLERANCE = 0.02  # fractions may wobble slightly between machines


def load_baseline(path: Path, backend: str, question_set: str) -> dict[str, float]:
    baselines = json.loads(path.read_text())
    try:
        return dict(baselines[backend][question_set])
    except KeyError as error:
        raise KeyError(f"No baseline for backend={backend!r}, set={question_set!r}") from error


def check_gates(summary: dict[str, float], baseline: dict[str, float]) -> list[str]:
    """Return one message per metric that is worse than the baseline (empty means pass)."""
    failures: list[str] = []
    for name in _HIGHER_IS_BETTER:
        slack = _TOLERANCE if name != "correct" else 0.0
        if summary[name] < baseline[name] - slack:
            failures.append(f"{name} fell to {summary[name]} (baseline {baseline[name]})")
    for name in _LOWER_IS_BETTER:
        if summary[name] > baseline[name]:
            failures.append(f"{name} rose to {summary[name]} (baseline {baseline[name]})")
    return failures
