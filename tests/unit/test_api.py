import secrets

import httpx
import pytest
from fastapi.testclient import TestClient

from citedesk.api.auth import InvalidTokenError, decode_token, issue_token
from citedesk.api.main import create_api
from citedesk.api.ratelimit import RateLimiter
from citedesk.bootstrap import App
from citedesk.config import Settings
from citedesk.ingestion.fetching import UrlFetcher
from citedesk.ingestion.service import IngestionService
from tests.conftest import SAMPLE_HANDBOOK

SECRET = secrets.token_urlsafe(32)  # random on every run, never written down
OTHER_SECRET = secrets.token_urlsafe(32)


def _headers(role: str, user: str = "tester", secret: str = SECRET) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(secret, user, role)}"}  # type: ignore[arg-type]


@pytest.fixture
def client(app: App) -> TestClient:
    settings = Settings(jwt_dev_secret=SECRET, rate_limit_per_minute=1000)
    return TestClient(create_api(app, settings))


def _add(client: TestClient, license: str | None = "CC0 (test)") -> str:
    response = client.post(
        "/v1/admin/documents",
        headers=_headers("admin"),
        json={
            "title": "Acme Handbook",
            "content": SAMPLE_HANDBOOK,
            "source_name": "tests",
            "license": license,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


# --- health and sign-in -------------------------------------------------------------------


def test_health_and_ready_need_no_sign_in(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json()["status"] == "ready"


def test_the_api_refuses_to_start_without_a_secret(app: App) -> None:
    with pytest.raises(RuntimeError, match="CITEDESK_JWT_DEV_SECRET"):
        create_api(app, Settings(jwt_dev_secret=None))


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Basic abc"},
        _headers("analyst", secret=OTHER_SECRET),
    ],
)
def test_requests_without_a_valid_token_get_401(
    client: TestClient, headers: dict[str, str]
) -> None:
    assert client.post("/v1/chat", json={"question": "hi"}, headers=headers).status_code == 401


def test_an_expired_token_is_rejected() -> None:
    token = issue_token(SECRET, "tester", "analyst", ttl_seconds=-10)
    with pytest.raises(InvalidTokenError):
        decode_token(SECRET, token)


# --- roles --------------------------------------------------------------------------------


def test_only_admins_may_manage_documents(client: TestClient) -> None:
    body = {"title": "t", "content": SAMPLE_HANDBOOK, "source_name": "s", "license": "x"}
    for role in ("analyst", "reviewer"):
        response = client.post("/v1/admin/documents", headers=_headers(role), json=body)
        assert response.status_code == 403
    assert client.get("/v1/admin/documents", headers=_headers("analyst")).status_code == 403
    assert client.get("/v1/admin/audit", headers=_headers("analyst")).status_code == 403


# --- the admin workflow and asking questions, end to end ----------------------------------


def test_full_workflow_add_preview_publish_ask_cite_unpublish(client: TestClient) -> None:
    document_id = _add(client)
    admin = _headers("admin")

    # A draft is invisible to questions.
    before = client.post(
        "/v1/chat",
        headers=_headers("analyst"),
        json={"question": "How many vacation days do I get?"},
    ).json()
    assert before["refused"] is True

    preview = client.get(f"/v1/admin/documents/{document_id}/preview", headers=admin).json()
    assert any(chunk["section_path"] == "Time off > Vacation" for chunk in preview)

    published = client.post(f"/v1/admin/documents/{document_id}/publish", headers=admin)
    assert published.json()["status"] == "published"

    answer = client.post(
        "/v1/chat",
        headers=_headers("analyst"),
        json={"question": "How many vacation days do I get?"},
    ).json()
    assert answer["refused"] is False
    assert "20 days" in answer["text"]
    citation = answer["citations"][0]
    assert citation["section_path"] == "Time off > Vacation"

    passage = client.get(f"/v1/chunks/{citation['chunk_id']}", headers=_headers("analyst"))
    assert passage.status_code == 200
    assert "20 days" in passage.json()["text"]

    client.post(f"/v1/admin/documents/{document_id}/unpublish", headers=admin)
    gone = client.get(f"/v1/chunks/{citation['chunk_id']}", headers=_headers("analyst"))
    assert gone.status_code == 404

    audit = client.get("/v1/admin/audit", headers=admin).json()
    assert [entry["action"] for entry in audit][:3] == ["retired", "published", "add"]
    assert audit[0]["actor"] == "tester"


def test_expected_problems_become_clear_status_codes(client: TestClient) -> None:
    admin = _headers("admin")
    document_id = _add(client, license=None)

    blocked = client.post(f"/v1/admin/documents/{document_id}/publish", headers=admin)
    assert blocked.status_code == 409
    assert "license" in blocked.json()["detail"]

    duplicate = client.post(
        "/v1/admin/documents",
        headers=admin,
        json={"title": "t", "content": SAMPLE_HANDBOOK, "source_name": "s"},
    )
    assert duplicate.status_code == 409

    too_short = client.post(
        "/v1/admin/documents",
        headers=admin,
        json={"title": "t", "content": "# Access denied", "source_name": "s"},
    )
    assert too_short.status_code == 422

    assert client.get("/v1/admin/documents/nope/preview", headers=admin).status_code == 404


def test_bad_input_is_rejected_before_it_reaches_the_pipeline(client: TestClient) -> None:
    analyst = _headers("analyst")
    assert client.post("/v1/chat", headers=analyst, json={"question": ""}).status_code == 422
    assert (
        client.post("/v1/chat", headers=analyst, json={"question": "x" * 1001}).status_code == 422
    )
    assert client.post("/v1/chat", headers=analyst, json={}).status_code == 422


def test_url_import_refuses_internal_addresses(client: TestClient) -> None:
    response = client.post(
        "/v1/admin/imports",
        headers=_headers("admin"),
        json={"url": "http://169.254.169.254/latest/meta-data", "source_name": "x"},
    )
    assert response.status_code == 400


def test_url_import_works_through_the_api(app: App) -> None:
    page = (
        "<html><body><h1>Remote Work</h1><p>Employees may work remotely up to three days a week "
        "with manager approval. Remote work needs a secure home network.</p></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    fetcher = UrlFetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda host: ["93.184.216.34"],
    )
    wired = App(
        ingestion=IngestionService(app.repository, app.embedder, app.index, fetcher),
        answers=app.answers,
        repository=app.repository,
        embedder=app.embedder,
        index=app.index,
        reranker=app.reranker,
    )
    api = TestClient(create_api(wired, Settings(jwt_dev_secret=SECRET)))
    response = api.post(
        "/v1/admin/imports",
        headers=_headers("admin"),
        json={"url": "https://example.com/remote", "source_name": "Example", "license": "CC0"},
    )
    assert response.status_code == 201
    assert response.json()["source_url"] == "https://example.com/remote"


# --- protection against abuse and leaks ---------------------------------------------------


def test_rate_limit_returns_429_after_too_many_requests(app: App) -> None:
    api = TestClient(create_api(app, Settings(jwt_dev_secret=SECRET, rate_limit_per_minute=3)))
    codes = [
        api.post(
            "/v1/chat", headers=_headers("analyst"), json={"question": "hello there"}
        ).status_code
        for _ in range(5)
    ]
    assert codes == [200, 200, 200, 429, 429]
    # Another user has their own allowance.
    other = api.post("/v1/chat", headers=_headers("analyst", user="other"), json={"question": "hi"})
    assert other.status_code == 200


def test_rate_limiter_forgets_old_requests() -> None:
    limiter = RateLimiter(per_minute=1)
    limiter.check("a", now=0.0)
    with pytest.raises(Exception, match="Too many"):
        limiter.check("a", now=30.0)
    limiter.check("a", now=61.0)


def test_responses_carry_a_request_id_and_security_headers(client: TestClient) -> None:
    response = client.get("/health")
    assert len(response.headers["x-request-id"]) == 12
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_unexpected_errors_do_not_leak_details(app: App) -> None:
    class Exploding:
        def ask(self, question: str) -> None:
            raise RuntimeError("database password is hunter2")

    broken = App(
        ingestion=app.ingestion,
        answers=Exploding(),  # type: ignore[arg-type]
        repository=app.repository,
        embedder=app.embedder,
        index=app.index,
        reranker=app.reranker,
    )
    api = TestClient(
        create_api(broken, Settings(jwt_dev_secret=SECRET)), raise_server_exceptions=False
    )
    response = api.post("/v1/chat", headers=_headers("analyst"), json={"question": "hello"})
    assert response.status_code == 500
    assert "hunter2" not in response.text


def test_interactive_docs_are_off_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_token_command_prints_a_token_that_the_api_accepts(
    app: App, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from citedesk.cli import main

    monkeypatch.setenv("CITEDESK_JWT_DEV_SECRET", SECRET)
    assert main(["token", "--user", "alice", "--role", "admin"]) == 0
    token = capsys.readouterr().out.strip()
    assert SECRET not in token
    principal = decode_token(SECRET, token)
    assert (principal.user_id, principal.role) == ("alice", "admin")


def test_token_command_needs_a_secret(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from citedesk.cli import main

    monkeypatch.delenv("CITEDESK_JWT_DEV_SECRET", raising=False)
    monkeypatch.chdir("/")  # so no .env file is read
    assert main(["token", "--user", "alice"]) == 1
    assert "CITEDESK_JWT_DEV_SECRET" in capsys.readouterr().err
