"""Answer writers: turn question + passages into text with [n] citation markers."""

from collections.abc import Sequence

from citedesk.domain.models import Passage
from citedesk.text import content_tokens, split_sentences

_MAX_SENTENCES = 3
# A passage is used only if its relevance is at least this share of the best passage's,
# so one strong match is not padded with weaker, unrelated sentences.
_MIN_SHARE_OF_BEST = 0.75


class ExtractiveAnswerWriter:
    """Builds the answer by quoting the passage sentences that best match the question.

    Every sentence is copied word for word from a passage, so it always passes the
    citation check. It works offline and is the default until a language-model writer is
    added (next ticket). The `strict` option makes no difference here because the
    output is already quote-only.
    """

    def write(self, question: str, passages: Sequence[Passage], *, strict: bool) -> str:
        wanted = set(content_tokens(question))
        best_score = max((p.score for p in passages), default=0.0)
        picks: list[str] = []
        for number, passage in enumerate(passages, start=1):
            if passage.score < best_score * _MIN_SHARE_OF_BEST:
                continue
            best = self._best_sentence(wanted, passage)
            if best is not None:
                picks.append(f"{best.rstrip('.!?')} [{number}].")
            if len(picks) == _MAX_SENTENCES:
                break
        return " ".join(picks)

    @staticmethod
    def _best_sentence(wanted: set[str], passage: Passage) -> str | None:
        scored = [
            (len(wanted & set(content_tokens(sentence))), sentence)
            for sentence in split_sentences(passage.text)
        ]
        overlap, sentence = max(scored, default=(0, ""), key=lambda pair: pair[0])
        return sentence if overlap > 0 else None
