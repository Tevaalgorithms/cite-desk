import pytest
from pydantic import SecretStr

from citedesk.adapters.openai_writer import OpenAIAnswerWriter
from citedesk.answer.writers import ExtractiveAnswerWriter
from citedesk.bootstrap import build_writer
from citedesk.config import Settings

KEY = "sk-this-is-a-fake-key-0123456789abcdef"


def test_the_default_writer_needs_no_key() -> None:
    assert isinstance(build_writer(Settings()), ExtractiveAnswerWriter)


def test_the_openai_writer_needs_a_key() -> None:
    with pytest.raises(RuntimeError, match="CITEDESK_OPENAI_API_KEY"):
        build_writer(Settings(writer="openai"))


def test_the_openai_writer_uses_the_configured_model() -> None:
    writer = build_writer(
        Settings(writer="openai", openai_api_key=SecretStr(KEY), openai_model="gpt-demo")
    )
    assert isinstance(writer, OpenAIAnswerWriter)
    assert writer.info().model == "gpt-demo"


def test_the_key_is_never_shown_when_settings_are_printed_or_logged() -> None:
    settings = Settings(openai_api_key=SecretStr(KEY))
    assert KEY not in repr(settings)
    assert KEY not in str(settings)
    assert KEY not in settings.model_dump_json()


def test_the_key_and_model_are_read_from_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CITEDESK_OPENAI_API_KEY", KEY)
    monkeypatch.setenv("CITEDESK_OPENAI_MODEL", "gpt-5.4-nano")
    monkeypatch.setenv("CITEDESK_WRITER", "openai")
    settings = Settings()
    assert settings.writer == "openai"
    assert settings.openai_model == "gpt-5.4-nano"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == KEY
