"""Tests that call the real OpenAI model. They cost a few cents and run only on request:

    CITEDESK_RUN_LLM_TESTS=1 uv run pytest tests/llm --no-cov

The key is read from your local `.env`. Mocks hide prompt and parameter problems (the real models
reject `max_tokens`, for example), so run these after changing the writer, its prompt or the model.
"""

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from citedesk.bootstrap import App, build_app
from citedesk.config import Settings
from citedesk.ops.ssm import read_env_file

ROOT = Path(__file__).resolve().parents[2]
_ENV = read_env_file(ROOT / ".env") if (ROOT / ".env").exists() else {}
_KEY = _ENV.get("CITEDESK_OPENAI_API_KEY", "")

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        os.environ.get("CITEDESK_RUN_LLM_TESTS") != "1" or not _KEY,
        reason="set CITEDESK_RUN_LLM_TESTS=1 and CITEDESK_OPENAI_API_KEY in .env to run",
    ),
]

HANDBOOK = (ROOT / "data" / "sample" / "acme-handbook.md").read_text()


@pytest.fixture
def live_app(tmp_path: Path) -> App:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'live.db'}",
        writer="openai",
        openai_api_key=SecretStr(_KEY),
        openai_model=_ENV.get("CITEDESK_OPENAI_MODEL", "gpt-5.4-nano"),
    )
    app = build_app(settings)
    document = app.ingestion.add_text(
        HANDBOOK, content_type="markdown", title=None, source_name="live test",
        actor="tester", license="CC0 (synthetic sample)",
    )  # fmt: skip
    app.ingestion.publish(document.id, actor="tester")
    return app


def test_the_real_model_answers_and_the_status_check_reports_live(live_app: App) -> None:
    health = live_app.model.check()
    assert health.state == "live", health.detail
    assert live_app.model.info().provider == "openai"

    answer = live_app.answers.ask("How many vacation days do I get?")

    assert not answer.refused, answer.refusal_reason
    assert "20" in answer.text
    assert answer.citations[0].section_path == "Time off > Vacation"
    usage = live_app.model.usage()
    assert usage is not None
    assert usage.calls >= 2
    assert usage.prompt_tokens > 0


def test_the_real_model_refuses_what_the_handbook_does_not_say(live_app: App) -> None:
    answer = live_app.answers.ask("What is the capital of France?")
    assert answer.refused


def test_a_wrong_key_is_reported_without_leaking_it(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'bad.db'}",
        writer="openai",
        openai_api_key=SecretStr("sk-this-key-is-not-valid-0123456789"),
    )
    health = build_app(settings).model.check()
    assert health.state == "error"
    assert "sk-this-key" not in health.detail
