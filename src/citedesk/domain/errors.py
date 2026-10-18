"""Errors shared by the answer flow and its writers."""


class WriterUnavailableError(RuntimeError):
    """The answer writer could not be reached (network, timeout, rate limit, bad credentials).

    The message must never contain a key or any request content.
    """
