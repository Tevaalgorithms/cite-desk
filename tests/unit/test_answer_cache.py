import threading
from collections.abc import Sequence

import pytest

from citedesk.answer.cache import AnswerCache, normalize_question
from citedesk.bootstrap import App
from citedesk.domain.models import Answer, Passage
from tests.conftest import SECOND_DOCUMENT


def _answer(text: str = "Staff get 20 days [1].", *, version: int = 1, **fields: object) -> Answer:
    return Answer(question="q", text=text, corpus_version=version, **fields)  # type: ignore[arg-type]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("How many days?", "how many days"),
        ("  How   many\tdays ??  ", "how many days"),
        ("HOW MANY DAYS.", "how many days"),
    ],
)
def test_questions_are_compared_after_tidying_case_spacing_and_end_punctuation(
    raw: str, expected: str
) -> None:
    assert normalize_question(raw) == expected


def test_a_stored_answer_comes_back_marked_as_cached() -> None:
    cache = AnswerCache()
    cache.put("How many days?", _answer(), "label")
    hit = cache.get("how many days", 1, "label")
    assert hit is not None
    assert hit.from_cache is True
    assert hit.text == "Staff get 20 days [1]."


def test_a_new_corpus_version_or_a_different_model_never_sees_old_answers() -> None:
    cache = AnswerCache()
    cache.put("q", _answer(version=1), "nano")
    assert cache.get("q", 2, "nano") is None  # content was published or removed
    assert cache.get("q", 1, "mini") is None  # a different model would answer differently
    assert cache.get("q", 1, "nano") is not None


def test_entries_expire() -> None:
    clock = Clock()
    cache = AnswerCache(ttl_seconds=60, clock=clock)
    cache.put("q", _answer(), "l")
    clock.now = 59
    assert cache.get("q", 1, "l") is not None
    clock.now = 61
    assert cache.get("q", 1, "l") is None


def test_the_least_recently_used_entry_is_dropped_when_full() -> None:
    cache = AnswerCache(max_entries=2)
    cache.put("a", _answer(), "l")
    cache.put("b", _answer(), "l")
    cache.get("a", 1, "l")  # a is now the most recently used
    cache.put("c", _answer(), "l")
    assert cache.get("b", 1, "l") is None
    assert cache.get("a", 1, "l") is not None
    assert cache.get("c", 1, "l") is not None


def test_only_answers_that_do_not_depend_on_luck_are_stored() -> None:
    cache = AnswerCache()
    stored = {
        "answered": _answer(),
        "nothing found": _answer("", refused=True, refusal_reason="nothing_relevant_found"),
        "passages do not answer": _answer(
            "", refused=True, refusal_reason="passages_do_not_answer"
        ),
    }
    never = {
        "model down": _answer("", refused=True, refusal_reason="model_unavailable"),
        "could not verify": _answer("", refused=True, refusal_reason="could_not_verify_answer"),
        "empty question": _answer("", refused=True, refusal_reason="empty_question"),
    }
    for name, answer in {**stored, **never}.items():
        cache.put(name, answer, "l")
    assert all(cache.get(name, 1, "l") is not None for name in stored)
    assert all(cache.get(name, 1, "l") is None for name in never)


def test_a_size_of_zero_turns_the_cache_off() -> None:
    cache = AnswerCache(max_entries=0)
    cache.put("q", _answer(), "l")
    assert not cache.enabled
    assert cache.get("q", 1, "l") is None


def test_many_threads_can_use_one_cache_safely() -> None:
    cache = AnswerCache(max_entries=50)

    def work(number: int) -> None:
        for i in range(200):
            cache.put(f"q{(number * i) % 80}", _answer(), "l")
            cache.get(f"q{i % 80}", 1, "l")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(cache._entries) <= 50  # never grows past its limit


# --- inside the answer service --------------------------------------------------------------


OTHER_DOCUMENT = (
    "# Other\n\n## Lunch\n\nThe cafeteria serves lunch from noon until two in the afternoon "
    "every weekday. Coffee and tea are free on every floor of the building."
)


class CountingWriter:
    def __init__(self) -> None:
        self.calls = 0

    def write(self, question: str, passages: Sequence[Passage], *, strict: bool) -> str:
        self.calls += 1
        return f"{passages[0].text.split('.')[0]} [1]."


def _publish(app: App, content: str, title: str) -> None:
    document = app.ingestion.add_text(
        content, content_type="markdown", title=title, source_name="t", actor="t", license="CC0"
    )
    app.ingestion.publish(document.id, actor="t")


def test_a_repeated_question_does_not_call_the_writer_again(make_app) -> None:  # type: ignore[no-untyped-def]
    writer = CountingWriter()
    app = make_app(writer)
    _publish(app, SECOND_DOCUMENT, "Security Policy")

    first = app.answers.ask("How long must passwords be?")
    second = app.answers.ask("  how long MUST passwords be ")

    assert not first.refused
    assert writer.calls == 1
    assert (first.from_cache, second.from_cache) == (False, True)
    assert second.text == first.text
    assert second.question == "  how long MUST passwords be "  # the asker's own wording is kept


def test_publishing_new_content_invalidates_remembered_answers(make_app) -> None:  # type: ignore[no-untyped-def]
    writer = CountingWriter()
    app = make_app(writer)
    _publish(app, SECOND_DOCUMENT, "Security Policy")
    app.answers.ask("How long must passwords be?")

    _publish(app, OTHER_DOCUMENT, "Other")
    again = app.answers.ask("How long must passwords be?")

    assert writer.calls == 2  # asked the writer again: the corpus changed
    assert again.from_cache is False
