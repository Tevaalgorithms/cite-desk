"""Shared test fixtures. The sample handbook below is synthetic text written for tests."""

import os
from pathlib import Path

import pytest

from citedesk.bootstrap import App, build_app
from citedesk.config import Settings
from citedesk.domain.ports import AnswerWriter

SAMPLE_HANDBOOK = """\
# Acme Handbook

## Time off

### Vacation

Full-time employees receive 20 days of paid vacation each year. Unused vacation days carry \
over for up to 5 days into the next year.

## Equipment

### Returning equipment

When you leave the company you must return your laptop within 5 business days. Contact IT \
to arrange a courier.

## Expenses

### Meals

Meals during business travel are reimbursed up to 60 dollars per day. Keep every receipt.
"""

SECOND_DOCUMENT = """\
# Security Policy

## Passwords

Passwords must be at least 14 characters long. Multi-factor authentication is required for \
every administrator account.
"""


@pytest.fixture(autouse=True)
def _isolate_from_local_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must behave the same on every machine: ignore any local `.env` file and any
    CITEDESK_* variables set in the developer's shell (for example CITEDESK_MODELS=local)."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in [key for key in os.environ if key.startswith("CITEDESK_")]:
        monkeypatch.delenv(name)


@pytest.fixture
def make_app(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Build an app on a throwaway SQLite database."""
    counter = 0

    def _make(writer: AnswerWriter | None = None) -> App:
        nonlocal counter
        counter += 1
        settings = Settings(database_url=f"sqlite:///{tmp_path / f'test{counter}.db'}")
        return build_app(settings, writer=writer)

    return _make


@pytest.fixture
def app(make_app) -> App:  # type: ignore[no-untyped-def]
    return make_app()


@pytest.fixture
def published_app(app: App) -> App:
    """An app with the sample handbook already published."""
    document = app.ingestion.add_text(
        SAMPLE_HANDBOOK,
        content_type="markdown",
        title="Acme Handbook",
        source_name="tests",
        actor="tester",
        license="CC0 (synthetic test text)",
    )
    app.ingestion.publish(document.id, actor="tester")
    return app
