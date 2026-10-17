"""Golden questions: questions with known answers, used to measure quality."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoldenCase:
    id: str
    category: str  # "exact", "paraphrase" or "unanswerable"
    question: str
    answerable: bool
    gold_sections: tuple[str, ...]  # section paths that answer the question


def load_golden_cases(path: Path) -> list[GoldenCase]:
    raw = json.loads(path.read_text())
    return [
        GoldenCase(
            id=item["id"],
            category=item["category"],
            question=item["question"],
            answerable=item["answerable"],
            gold_sections=tuple(item["gold_sections"]),
        )
        for item in raw
    ]
