import itertools

from citedesk.ingestion.chunking import chunk_document
from citedesk.ingestion.parsing import ParsedDocument, Section


def _document(*sections: tuple[str, str]) -> ParsedDocument:
    return ParsedDocument("Doc", tuple(Section(path, text) for path, text in sections))


def test_short_section_is_one_chunk() -> None:
    chunks = chunk_document(_document(("A", "First sentence. Second sentence.")))
    assert [c.text for c in chunks] == ["First sentence. Second sentence."]


def test_chunks_never_cross_sections() -> None:
    chunks = chunk_document(_document(("A", "Alpha one."), ("B", "Beta one.")))
    assert [(c.section_path, c.text) for c in chunks] == [("A", "Alpha one."), ("B", "Beta one.")]


def test_long_section_is_split_with_one_sentence_of_overlap() -> None:
    sentences = [f"Sentence number {n} is here." for n in range(1, 9)]
    chunks = chunk_document(_document(("A", " ".join(sentences))), max_chars=80)

    assert len(chunks) > 1
    for earlier, later in itertools.pairwise(chunks):
        last_sentence_of_earlier = earlier.text.split(". ")[-1]
        assert later.text.startswith(last_sentence_of_earlier.rstrip("."))
    covered = " ".join(c.text for c in chunks)
    assert all(sentence in covered for sentence in sentences)


def test_one_oversized_sentence_still_becomes_a_chunk() -> None:
    chunks = chunk_document(_document(("A", "word " * 100 + "end.")), max_chars=50)
    assert len(chunks) == 1
