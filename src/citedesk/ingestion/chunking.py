"""Split parsed sections into passage-sized chunks."""

from collections.abc import Iterator
from dataclasses import dataclass

from citedesk.ingestion.parsing import ParsedDocument
from citedesk.text import split_sentences


@dataclass(frozen=True)
class ChunkDraft:
    section_path: str
    text: str


def chunk_document(
    document: ParsedDocument, *, max_chars: int = 1200, overlap_sentences: int = 1
) -> list[ChunkDraft]:
    """Cut each section into chunks of at most about `max_chars` characters.

    Chunks never cross a section boundary, so a citation can always name its section.
    When a section is long, consecutive chunks share `overlap_sentences` sentences so a
    fact split across a boundary is still found whole in one of them.
    """
    drafts: list[ChunkDraft] = []
    for section in document.sections:
        sentences = split_sentences(section.text)
        drafts.extend(
            ChunkDraft(section_path=section.path, text=text)
            for text in _windows(sentences, max_chars, overlap_sentences)
        )
    return drafts


def _windows(sentences: list[str], max_chars: int, overlap: int) -> Iterator[str]:
    window: list[str] = []
    size = 0
    has_new_sentence = False  # False while the window holds only overlap from the last chunk

    for sentence in sentences:
        if has_new_sentence and size + len(sentence) + 1 > max_chars:
            yield " ".join(window)
            window = window[-overlap:] if overlap else []
            size = sum(len(kept) + 1 for kept in window)
            has_new_sentence = False
        window.append(sentence)
        size += len(sentence) + 1
        has_new_sentence = True

    if has_new_sentence:
        yield " ".join(window)
