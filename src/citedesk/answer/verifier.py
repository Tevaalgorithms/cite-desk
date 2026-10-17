"""Citation enforcement: check that every sentence of an answer is backed by its sources.

The checks are deterministic code, not a model, so they behave the same way every time.

Answer format the writer must follow: each sentence ends with one or more markers like
`[2]` placed before the final full stop, for example `You get 20 days [1].`
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from citedesk.domain.models import Passage
from citedesk.text import content_tokens, split_sentences

_MARKER = re.compile(r"\[(\d+)\]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_QUOTE = re.compile(r'"([^"]{4,})"')

# Share of a sentence's content words that must appear in the passages it cites.
MIN_SUPPORT = 0.6


@dataclass(frozen=True)
class Verification:
    passed: bool
    problems: tuple[str, ...] = ()


def cited_markers(answer: str) -> list[int]:
    """Marker numbers used in an answer, in order of first use, without repeats."""
    seen: dict[int, None] = {}
    for match in _MARKER.finditer(answer):
        seen.setdefault(int(match.group(1)))
    return list(seen)


def verify_answer(answer: str, passages: Sequence[Passage]) -> Verification:
    """Check every sentence. `passages[0]` is marker [1], `passages[1]` is [2], and so on."""
    sentences = split_sentences(answer)
    if not sentences:
        return Verification(False, ("The answer is empty.",))

    problems: list[str] = []
    for sentence in sentences:
        problems.extend(_check_sentence(sentence, passages))
    return Verification(passed=not problems, problems=tuple(problems))


def _check_sentence(sentence: str, passages: Sequence[Passage]) -> list[str]:
    markers = [int(number) for number in _MARKER.findall(sentence)]
    if not markers:
        return [f"No citation: {sentence!r}"]

    unknown = [number for number in markers if not 1 <= number <= len(passages)]
    if unknown:
        return [f"Unknown citation {unknown} in: {sentence!r}"]

    cited_text = " ".join(passages[number - 1].text for number in markers)
    claim = _MARKER.sub("", sentence)
    problems: list[str] = []

    for quote in _QUOTE.findall(claim):
        if quote.lower() not in cited_text.lower():
            problems.append(f"Quoted text not found in the cited passage: {quote!r}")

    for number in _NUMBER.findall(claim):
        if number not in cited_text:
            problems.append(f"Number {number} does not appear in the cited passage: {sentence!r}")

    words = content_tokens(claim)
    if words:
        cited_words = set(content_tokens(cited_text))
        support = sum(word in cited_words for word in words) / len(words)
        if support < MIN_SUPPORT:
            problems.append(f"Only {support:.0%} of the words are supported: {sentence!r}")
    return problems
