import httpx
import pytest

from citedesk.ingestion.fetching import FetchError, UnsafeUrlError, UrlFetcher

HOSTS = {
    "example.com": ["93.184.216.34"],
    "internal.example": ["10.0.0.5"],
    "metadata.example": ["169.254.169.254"],
}
PAGE = "<html><body><h1>Hi</h1><p>Some page text.</p></body></html>"


def _fetcher(handler, **options) -> UrlFetcher:  # type: ignore[no-untyped-def]
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return UrlFetcher(client, resolver=lambda host: HOSTS[host], **options)


def _site(routes: dict[str, httpx.Response]):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return handler


HTML = {"content-type": "text/html; charset=utf-8"}


def test_fetches_a_public_page() -> None:
    fetcher = _fetcher(
        _site({"https://example.com/page": httpx.Response(200, text=PAGE, headers=HTML)})
    )
    page = fetcher.fetch("https://example.com/page")
    assert page.content_type == "html"
    assert "Some page text" in page.text


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "https://internal.example/x",
        "http://metadata.example/latest/meta-data",
    ],
)
def test_refuses_non_public_destinations(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        _fetcher(_site({})).fetch(url)


def test_checks_every_redirect_hop() -> None:
    routes = {
        "https://example.com/go": httpx.Response(
            302, headers={"location": "http://internal.example/x"}
        ),
    }
    with pytest.raises(UnsafeUrlError):
        _fetcher(_site(routes)).fetch("https://example.com/go")


def test_follows_a_safe_redirect() -> None:
    routes = {
        "https://example.com/old": httpx.Response(301, headers={"location": "/new"}),
        "https://example.com/new": httpx.Response(200, text=PAGE, headers=HTML),
    }
    assert _fetcher(_site(routes)).fetch("https://example.com/old").url == "https://example.com/new"


def test_stops_after_too_many_redirects() -> None:
    routes = {"https://example.com/loop": httpx.Response(302, headers={"location": "/loop"})}
    with pytest.raises(FetchError, match="Too many redirects"):
        _fetcher(_site(routes)).fetch("https://example.com/loop")


def test_respects_robots_txt() -> None:
    routes = {
        "https://example.com/robots.txt": httpx.Response(
            200, text="User-agent: *\nDisallow: /private", headers={"content-type": "text/plain"}
        ),
        "https://example.com/private/a": httpx.Response(200, text=PAGE, headers=HTML),
    }
    with pytest.raises(FetchError, match=r"robots\.txt"):
        _fetcher(_site(routes)).fetch("https://example.com/private/a")


def test_does_not_fetch_when_robots_txt_cannot_be_read() -> None:
    routes = {"https://example.com/robots.txt": httpx.Response(500)}
    with pytest.raises(FetchError, match=r"robots\.txt"):
        _fetcher(_site(routes)).fetch("https://example.com/page")


def test_rejects_oversized_pages() -> None:
    routes = {"https://example.com/big": httpx.Response(200, text="x" * 1000, headers=HTML)}
    with pytest.raises(FetchError, match="larger than"):
        _fetcher(_site(routes), max_bytes=100).fetch("https://example.com/big")


def test_rejects_unsupported_content_types() -> None:
    routes = {
        "https://example.com/file": httpx.Response(
            200, content=b"%PDF", headers={"content-type": "application/pdf"}
        )
    }
    with pytest.raises(FetchError, match="Unsupported"):
        _fetcher(_site(routes)).fetch("https://example.com/file")
