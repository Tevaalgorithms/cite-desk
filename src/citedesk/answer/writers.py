"""Answer writers: turn question + passages into text with [n] citation markers."""

from collections.abc import Sequence

from citedesk.domain.models import Passage
from citedesk.text import content_tokens, split_sentences


class ExtractiveAnswerWriter:
    """Answers by quoting the best-matching sentence of the best passage.

    The sentence is copied word for word, so it always passes the citation check. It uses only
    the top passage: adding sentences from lower-ranked passages cited unrelated sections in
    testing, because scores of weaker passages are too close to the best one to tell them
    apart. Combining several passages needs a language-model writer (next ticket). The
    `strict` option makes no difference because the output is already quote-only.
    """

    def write(self, question: str, passages: Sequence[Passage], *, strict: bool) -> str:
        if not passages:
            return ""
        sentence = self._best_sentence(set(content_tokens(question)), passages[0])
        return f"{sentence.rstrip('.!?')} [1]." if sentence else ""

    @staticmethod
    def _best_sentence(wanted: set[str], passage: Passage) -> str | None:
        sentences = split_sentences(passage.text)
        if not sentences:
            return None
        scored = [(len(wanted & set(content_tokens(sentence))), sentence) for sentence in sentences]
        overlap, best = max(scored, key=lambda pair: pair[0])
        # A paraphrased question may share no words with the passage. The reranker has already
        # judged the passage relevant, so lead with its first sentence.
        return best if overlap > 0 else sentences[0]
