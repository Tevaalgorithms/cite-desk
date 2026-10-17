"""Fetch web pages safely for admin URL import.

Guards: only http/https, only public IP addresses (no internal networks or cloud metadata
endpoints), a limit on redirects and size, robots.txt honoured, and a declared User-Agent.

Known limitation: the host is checked before connecting, but the HTTP client resolves it
again. A hostile DNS server could answer differently the second time. Run the importer in
a network-restricted environment in production (see docs/architecture/deployment.md).
"""

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from citedesk.ingestion.parsing import ContentType

USER_AGENT = "CiteDeskBot/0.1 (+https://github.com/Tevaalgorithms/cite-desk)"

_CONTENT_TYPES: dict[str, ContentType] = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/markdown": "markdown",
    "text/plain": "text",
}

HostResolver = Callable[[str], Sequence[str]]


class UnsafeUrlError(ValueError):
    """The URL points somewhere we must not fetch from."""


class FetchError(RuntimeError):
    """The page could not be fetched or is not usable."""


@dataclass(frozen=True)
class FetchedPage:
    url: str
    content_type: ContentType
    text: str


def resolve_host(host: str) -> list[str]:
    """Return every IP address the host name resolves to."""
    try:
        return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]
    except socket.gaierror as error:
        raise FetchError(f"Cannot resolve host {host!r}") from error


class UrlFetcher:
    def __init__(
        self,
        client: httpx.Client | None = None,
        resolver: HostResolver = resolve_host,
        *,
        max_bytes: int = 5_000_000,
        max_redirects: int = 3,
    ) -> None:
        self._client = client or httpx.Client(timeout=15.0)
        self._resolver = resolver
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects

    def fetch(self, url: str) -> FetchedPage:
        """Fetch one page, or raise `UnsafeUrlError` / `FetchError`."""
        self._check_url_is_public(url)
        if not self._robots_allow(url):
            raise FetchError("robots.txt does not allow fetching this page")
        body, final_url, mime = self._get(url)
        content_type = _CONTENT_TYPES.get(mime)
        if content_type is None:
            raise FetchError(f"Unsupported content type {mime!r}")
        return FetchedPage(url=final_url, content_type=content_type, text=body)

    def _check_url_is_public(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise UnsafeUrlError("Only http and https URLs with a host name are allowed")
        for address in self._resolver(parts.hostname):
            if not ipaddress.ip_address(address).is_global:
                raise UnsafeUrlError(f"{parts.hostname} resolves to a non-public address")

    def _get(self, url: str) -> tuple[str, str, str]:
        """GET with manual redirect handling so every hop is checked. Returns (body, url, mime)."""
        current = url
        for _ in range(self._max_redirects + 1):
            self._check_url_is_public(current)
            with self._client.stream(
                "GET", current, headers={"User-Agent": USER_AGENT}, follow_redirects=False
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("Redirect without a Location header")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise FetchError(f"HTTP {response.status_code} for {current}")
                mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
                return self._read_limited(response), current, mime
        raise FetchError("Too many redirects")

    def _read_limited(self, response: httpx.Response) -> str:
        received = bytearray()
        for piece in response.iter_bytes():
            received.extend(piece)
            if len(received) > self._max_bytes:
                raise FetchError(f"Page is larger than {self._max_bytes} bytes")
        return received.decode(response.encoding or "utf-8", errors="replace")

    def _robots_allow(self, url: str) -> bool:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            robots_text, _, _ = self._get(robots_url)
        except FetchError as error:
            # A missing robots.txt (404) means "no rules"; any other failure means we
            # cannot tell, so we do not fetch.
            return "HTTP 404" in str(error)
        parser = RobotFileParser()
        parser.parse(robots_text.splitlines())
        return parser.can_fetch(USER_AGENT, url)
