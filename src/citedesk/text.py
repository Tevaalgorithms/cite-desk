"""Small text helpers used by both ingestion and the answer flow."""

import re

# Filler words ignored when comparing a question with a passage. Generic question words
# such as "many", "long" and "must" are included: matching on them alone made unrelated
# passages look relevant.
_FILLER_WORDS = """
a about also an and any are as at be but by can could do does for from get has have how
i if in into is it its long many may might much must my need of on or our should so that
the their them then there these they this to was we were what when where which who will
with would you your
"""
STOPWORDS = frozenset(_FILLER_WORDS.split())

_TOKEN = re.compile(r"[a-z0-9]+")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def tokenize(text: str) -> list[str]:
    """Lower-case words and numbers."""
    return _TOKEN.findall(text.lower())


def content_tokens(text: str) -> list[str]:
    """Like `tokenize`, but without common filler words."""
    return [token for token in tokenize(text) if token not in STOPWORDS]


def split_sentences(text: str) -> list[str]:
    """Split text into sentences. Whitespace and line breaks are normalised first."""
    flattened = " ".join(text.split())
    return [part for part in _SENTENCE_BREAK.split(flattened) if part]
