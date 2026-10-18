"""A simple in-memory limit on requests per user per minute.

It is per process, so with several instances each one counts separately. A shared store
(for example Redis) is planned if the API ever runs on more than one instance.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from citedesk.api.auth import Principal


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self._per_minute = per_minute
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, now: float | None = None) -> None:
        """Record one request, or raise 429 if the user is over the limit."""
        moment = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and moment - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= self._per_minute:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down")
        hits.append(moment)


def enforce(request: Request, principal: Principal) -> None:
    request.app.state.rate_limiter.check(principal.user_id)
