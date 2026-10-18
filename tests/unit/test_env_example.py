"""`.env.example` is the checklist new developers copy, and it is committed to git. Keep it
complete and make sure no real secret can ever be put in it."""

import re
from pathlib import Path

import pytest

from citedesk.config import Settings

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"
_LINE = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]+)=(.*)$")
# Whole words only: OPENAI_API_KEY is a secret, MAX_OUTPUT_TOKENS is not.
_SECRET_NAME = re.compile(r"(^|_)(KEY|SECRET|TOKEN|PASSWORD)($|_)")
_SECRET_LOOKING_VALUE = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|pcsk_|pc-[A-Za-z0-9]{10,}|lsv2_|ls__|AKIA[0-9A-Z]{12,})"
)


def _entries() -> list[tuple[bool, str, str]]:
    """(is_active, name, value) for every setting, whether or not it is commented out."""
    found = []
    for line in EXAMPLE.read_text().splitlines():
        match = _LINE.match(line.rstrip())
        if match:
            found.append((match.group(1) is None, match.group(2), match.group(3).strip()))
    return found


def test_every_setting_the_app_reads_is_listed() -> None:
    listed = {name for _, name, _ in _entries()}
    missing = [
        f"CITEDESK_{field.upper()}" for field in Settings.model_fields
        if f"CITEDESK_{field.upper()}" not in listed
    ]  # fmt: skip
    assert not missing, f"add these to .env.example: {missing}"


def test_every_variable_the_compose_file_reads_is_listed() -> None:
    compose = (ROOT / "infrastructure" / "docker" / "compose.yml").read_text()
    used = set(re.findall(r"\$\{(CITEDESK_[A-Z_]+)", compose))
    listed = {name for _, name, _ in _entries()}
    assert used, "expected the compose file to use CITEDESK_* variables"
    assert used <= listed, f"add these to .env.example: {sorted(used - listed)}"


def test_no_secret_can_be_committed_in_the_example_file() -> None:
    for active, name, value in _entries():
        if _SECRET_NAME.search(name):
            assert value == "", f"{name} must stay empty in .env.example (active={active})"
        assert not _SECRET_LOOKING_VALUE.search(value), f"{name} looks like a real key"


def test_the_example_values_are_valid_settings() -> None:
    settings = Settings(_env_file=EXAMPLE)  # type: ignore[call-arg]
    assert settings.models == "offline"
    assert settings.database_url.startswith("sqlite:")
    assert settings.cors_origins == ["http://localhost:3000"]


def test_a_throwaway_server_can_ignore_every_settings_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CITEDESK_ENV_FILE=/dev/null makes Settings ignore a developer's .env, so test servers cannot
    pick up real keys or point at the real Pinecone index."""
    import importlib

    from citedesk import config

    env_file = tmp_path / "real.env"
    env_file.write_text("CITEDESK_VECTOR_INDEX=pinecone\nCITEDESK_WRITER=openai\n")
    try:
        monkeypatch.setenv("CITEDESK_ENV_FILE", str(env_file))
        importlib.reload(config)
        assert config.Settings.model_config["env_file"] == str(env_file)

        monkeypatch.setenv("CITEDESK_ENV_FILE", "/dev/null")
        importlib.reload(config)
        # the pointed-at file is ignored: /dev/null is empty, so defaults apply
        ignored = config.Settings(_env_file="/dev/null")  # type: ignore[call-arg]
        assert ignored.vector_index == "memory"
        assert ignored.writer == "extractive"
    finally:
        monkeypatch.delenv("CITEDESK_ENV_FILE", raising=False)
        importlib.reload(config)
