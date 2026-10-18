"""Tests against the real LangSmith service, in a throwaway project that is deleted afterwards.

    CITEDESK_RUN_LANGSMITH_TESTS=1 uv run pytest tests/langsmith --no-cov

They use the real OpenAI model too (a few cents), so the model call appears inside the trace.
"""

import contextlib
import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from citedesk.bootstrap import App, build_app
from citedesk.config import Settings
from citedesk.ops.ssm import read_env_file
from langsmith import Client

ROOT = Path(__file__).resolve().parents[2]
_ENV = read_env_file(ROOT / ".env") if (ROOT / ".env").exists() else {}
_LANGSMITH_KEY = _ENV.get("CITEDESK_LANGSMITH_API_KEY", "")
_OPENAI_KEY = _ENV.get("CITEDESK_OPENAI_API_KEY", "")

pytestmark = [
    pytest.mark.live_traces,
    pytest.mark.skipif(
        os.environ.get("CITEDESK_RUN_LANGSMITH_TESTS") != "1"
        or not (_LANGSMITH_KEY and _OPENAI_KEY),
        reason="set CITEDESK_RUN_LANGSMITH_TESTS=1 with LangSmith and OpenAI keys in .env to run",
    ),
]
HANDBOOK = (ROOT / "data" / "sample" / "acme-handbook.md").read_text()


@pytest.fixture
def project() -> Iterator[str]:
    name = f"cite-desk-test-{uuid.uuid4().hex[:8]}"
    yield name
    client = Client(api_key=_LANGSMITH_KEY)
    with contextlib.suppress(Exception):  # cleanup must not hide the real test result
        client.delete_project(project_name=name)


def _app(tmp_path: Path, project: str, *, hide: bool) -> App:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 't.db'}",
        writer="openai",
        openai_api_key=SecretStr(_OPENAI_KEY),
        langsmith_tracing=True,
        langsmith_api_key=SecretStr(_LANGSMITH_KEY),
        langsmith_project=project,
        langsmith_hide_content=hide,
        environment="test",
        answer_cache_size=0,
    )
    app = build_app(settings)
    document = app.ingestion.add_text(
        HANDBOOK, content_type="markdown", title=None, source_name="live test",
        actor="tester", license="CC0 (synthetic sample)",
    )  # fmt: skip
    app.ingestion.publish(document.id, actor="tester")
    return app


def _wait_for_runs(project: str, *, expect: int, seconds: float = 60.0) -> list[Any]:
    client = Client(api_key=_LANGSMITH_KEY)
    deadline = time.monotonic() + seconds
    while True:
        runs = list(client.list_runs(project_name=project, is_root=True))
        if len(runs) >= expect or time.monotonic() > deadline:
            return runs
        time.sleep(2)


def test_an_answer_appears_in_langsmith_with_its_steps_and_the_model_call(
    tmp_path: Path, project: str
) -> None:
    app = _app(tmp_path, project, hide=False)
    answer = app.answers.ask("How many vacation days do I get?")
    assert not answer.refused
    app.tracer.flush()

    runs = _wait_for_runs(project, expect=1)
    assert runs, "no trace arrived within a minute"
    root = runs[0]
    assert root.name == "cite-desk answer"
    assert root.extra["metadata"]["environment"] == "test"
    assert root.extra["metadata"]["model"] == "gpt-5.4-nano"
    assert root.extra["metadata"]["corpus_version"] == "1"

    # Steps inside a trace arrive a little after the trace itself, so wait for them too.
    client = Client(api_key=_LANGSMITH_KEY)
    wanted = {"retrieve", "write", "verify"}
    deadline = time.monotonic() + 60
    while True:
        names = {run.name for run in client.list_runs(project_name=project, trace_id=root.trace_id)}
        if wanted <= names or time.monotonic() > deadline:
            break
        time.sleep(2)
    assert wanted <= names, names
    assert any("openai" in name.lower() for name in names), names  # the model call is nested inside
    assert "20 days" in str(root.outputs)  # content is visible when it is not hidden


def test_hidden_content_never_reaches_langsmith(tmp_path: Path, project: str) -> None:
    app = _app(tmp_path, project, hide=True)
    app.answers.ask("How many vacation days do I get?")
    app.tracer.flush()

    runs = _wait_for_runs(project, expect=1)
    assert runs, "no trace arrived within a minute"
    text = f"{runs[0].inputs} {runs[0].outputs}"
    assert "vacation" not in text.lower()
    assert "20 days" not in text
    assert (
        runs[0].extra["metadata"]["environment"] == "test"
    )  # steps and metadata are still recorded
