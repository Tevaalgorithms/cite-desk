"""Combine several ranked lists into one."""

from collections import defaultdict
from collections.abc import Sequence


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], *, k: int = 60
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion.

    Each list gives an item `1 / (k + rank)` points (rank starts at 1); points add up
    across lists. Only positions matter, so keyword scores and vector similarities, which
    are on different scales, can be combined without any tuning.
    """
    points: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            points[item] += 1.0 / (k + position)
    return sorted(points.items(), key=lambda pair: pair[1], reverse=True)
