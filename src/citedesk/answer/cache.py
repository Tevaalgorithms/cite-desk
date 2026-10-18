"""Remember verified answers so a repeated question costs nothing.

It is an exact-match cache: the question is lower-cased and tidied, nothing fuzzy. The key also
holds the corpus version and a label for the writer and settings, so publishing a document,
unpublishing one, or switching the model automatically stops old answers from being served. The
cache lives in memory in one process, which is why the MVP runs a single API container.

Only answers that do not depend on luck are stored: a verified answer, or a refusal that follows
from the documents. A model outage or an answer that failed verification is never stored.
"""

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from citedesk.domain.models import Answer

# Refusals that follow from the documents, so they would repeat. Others (model down, could not
# verify) may succeed next time.
_STABLE_REFUSALS = frozenset({"nothing_relevant_found", "passages_do_not_answer"})


def normalize_question(question: str) -> str:
    collapsed = " ".join(question.lower().split())
    return re.sub(r"[\s?!.]+$", "", collapsed)


class AnswerCache:
    def __init__(
        self,
        max_entries: int = 500,
        ttl_seconds: float = 3600.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, int, str], tuple[float, Answer]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self._max_entries > 0

    def get(self, question: str, corpus_version: int, label: str) -> Answer | None:
        key = (normalize_question(question), corpus_version, label)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or self._clock() - entry[0] > self._ttl:
                self._entries.pop(key, None)
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return entry[1].model_copy(update={"from_cache": True})

    def put(self, question: str, answer: Answer, label: str) -> None:
        if not self.enabled or not _worth_storing(answer):
            return
        key = (normalize_question(question), answer.corpus_version, label)
        with self._lock:
            self._entries[key] = (self._clock(), answer)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


def _worth_storing(answer: Answer) -> bool:
    return not answer.refused or answer.refusal_reason in _STABLE_REFUSALS
