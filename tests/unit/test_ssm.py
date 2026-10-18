"""SSM secret handling, tested against a fake AWS: nothing here touches a real account."""

import json
import os
import stat
from collections.abc import Sequence
from pathlib import Path

import pytest

from citedesk.cli import main
from citedesk.ops.ssm import (
    DEFAULT_PATH,
    CommandResult,
    ParameterStore,
    SsmError,
    fingerprint,
    parameter_type,
    read_env_file,
)

SECRET = "sk-test-0123456789-not-a-real-key"
PATH = "/citedesk/test/"


class FakeAws:
    """Pretends to be the `aws` command line and remembers what it was asked to do."""

    def __init__(self) -> None:
        self.parameters: dict[str, dict[str, object]] = {}
        self.calls: list[list[str]] = []
        self.temp_files: list[str] = []
        self.fail_with: str | None = None

    def __call__(self, arguments: Sequence[str]) -> CommandResult:
        arguments = list(arguments)
        self.calls.append(arguments)
        if self.fail_with:
            return CommandResult(255, "", f"warning\n{self.fail_with}")
        if arguments[1] == "put-parameter":
            temp = arguments[arguments.index("--cli-input-json") + 1].removeprefix("file://")
            self.temp_files.append(temp)
            assert stat.S_IMODE(os.stat(temp).st_mode) == 0o600  # private while it exists
            body = json.loads(Path(temp).read_text())
            version = int(self.parameters.get(body["Name"], {}).get("Version", 0)) + 1  # type: ignore[call-overload]
            self.parameters[body["Name"]] = {**body, "Version": version}
            return CommandResult(0, "{}", "")
        decrypt = "--with-decryption" in arguments
        items = [
            {
                "Name": name,
                "Type": p["Type"],
                "Version": p["Version"],
                "LastModifiedDate": "2026-10-18T00:00:00Z",
                "Value": p["Value"] if decrypt else "AQICAHj-ciphertext",
            }
            for name, p in self.parameters.items()
        ]
        return CommandResult(0, json.dumps({"Parameters": items}), "")


@pytest.fixture
def aws() -> FakeAws:
    return FakeAws()


@pytest.fixture
def store(aws: FakeAws) -> ParameterStore:
    return ParameterStore(PATH, run=aws)


def test_push_creates_secure_strings_tagged_and_named_after_the_variable(
    store: ParameterStore, aws: FakeAws
) -> None:
    outcome = store.push({"CITEDESK_OPENAI_API_KEY": SECRET})
    assert outcome == {"CITEDESK_OPENAI_API_KEY": "created"}
    stored = aws.parameters[f"{PATH}CITEDESK_OPENAI_API_KEY"]
    assert stored["Type"] == "SecureString"
    assert stored["Overwrite"] is False
    assert {"Key": "project", "Value": "citedesk"} in stored["Tags"]  # type: ignore[operator]


def test_secret_values_never_appear_on_a_command_line_and_temp_files_are_removed(
    store: ParameterStore, aws: FakeAws
) -> None:
    store.push({"CITEDESK_OPENAI_API_KEY": SECRET})
    assert all(SECRET not in " ".join(call) for call in aws.calls)
    assert aws.temp_files
    assert not any(Path(name).exists() for name in aws.temp_files)


def test_existing_parameters_are_kept_unless_overwrite_is_asked_for(
    store: ParameterStore, aws: FakeAws
) -> None:
    store.push({"CITEDESK_OPENAI_API_KEY": SECRET})
    assert store.push({"CITEDESK_OPENAI_API_KEY": "different"}) == {
        "CITEDESK_OPENAI_API_KEY": "kept"
    }
    assert aws.parameters[f"{PATH}CITEDESK_OPENAI_API_KEY"]["Value"] == SECRET

    assert store.push({"CITEDESK_OPENAI_API_KEY": "different"}, overwrite=True) == {
        "CITEDESK_OPENAI_API_KEY": "updated"
    }
    updated = aws.parameters[f"{PATH}CITEDESK_OPENAI_API_KEY"]
    assert updated["Value"] == "different"
    assert updated["Version"] == 2
    assert "Tags" not in updated  # tags can only be set on creation


def test_list_returns_names_and_versions_but_never_asks_for_decryption(
    store: ParameterStore, aws: FakeAws
) -> None:
    store.push({"CITEDESK_OPENAI_API_KEY": SECRET})
    infos = store.list_parameters()
    assert [(i.name, i.type, i.version) for i in infos] == [
        (f"{PATH}CITEDESK_OPENAI_API_KEY", "SecureString", 1)
    ]
    assert not any(
        "--with-decryption" in call
        for call in aws.calls
        if call[1] == "get-parameters-by-path" and call is aws.calls[-1]
    )


def test_verify_compares_by_fingerprint(store: ParameterStore) -> None:
    store.push({"A_KEY": "one", "B_KEY": "two"})
    report = store.verify({"A_KEY": "one", "B_KEY": "changed", "C_KEY": "three"})
    assert report == {"A_KEY": "match", "B_KEY": "DIFFERENT", "C_KEY": "missing in SSM"}
    assert fingerprint("one") != fingerprint("two")


def test_pull_writes_an_owner_only_settings_file_with_safe_quoting(
    store: ParameterStore, tmp_path: Path
) -> None:
    store.push({"PLAIN_KEY": "abc-123", "SPACED_KEY": 'has space and "quote"'})
    destination = tmp_path / "prod.env"
    names = store.write_env_file(destination)
    assert names == ["PLAIN_KEY", "SPACED_KEY"]
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert read_env_file(destination)["PLAIN_KEY"] == "abc-123"
    assert 'SPACED_KEY="has space and \\"quote\\""' in destination.read_text()
    only = tmp_path / "only.env"
    assert store.write_env_file(only, only=["PLAIN_KEY"]) == ["PLAIN_KEY"]


def test_aws_failures_become_short_errors_without_values(aws: FakeAws) -> None:
    aws.fail_with = "An error occurred (AccessDeniedException) when calling PutParameter"
    store = ParameterStore(PATH, run=aws)
    with pytest.raises(SsmError, match="AccessDeniedException"):
        store.push({"A_KEY": SECRET})


def test_bad_names_paths_and_empty_values_are_refused(store: ParameterStore) -> None:
    with pytest.raises(ValueError, match="path"):
        ParameterStore("citedesk/prod")
    with pytest.raises(ValueError, match="environment variable"):
        store.parameter_name("lower-case")
    with pytest.raises(SsmError, match="empty"):
        store.push({"A_KEY": ""})


def test_read_env_file_handles_quotes_comments_and_blank_lines(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text('# comment\n\nA_KEY=plain\nB_KEY="quoted value"\nC_KEY=\n  D_KEY = ignored\n')
    assert read_env_file(env) == {"A_KEY": "plain", "B_KEY": "quoted value", "C_KEY": ""}


# --- the command line ---------------------------------------------------------------------


def test_cli_push_list_verify_and_pull_never_print_secret_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    aws = FakeAws()
    monkeypatch.setattr("citedesk.cli._store", lambda args: ParameterStore(args.path, run=aws))
    env = tmp_path / ".env"
    env.write_text(
        f"CITEDESK_OPENAI_API_KEY={SECRET}\nCITEDESK_PINECONE_API_KEY=pc-{SECRET}\n"
        f"CITEDESK_LANGSMITH_API_KEY=ls-{SECRET}\n"
    )
    out = tmp_path / "prod.env"

    assert main(["ssm", "push", "--env-file", str(env)]) == 0
    assert main(["ssm", "push", "--env-file", str(env)]) == 0  # second time: kept
    assert main(["ssm", "list"]) == 0
    assert main(["ssm", "verify", "--env-file", str(env)]) == 0
    assert main(["ssm", "pull", "--out", str(out)]) == 0

    shown = capsys.readouterr()
    assert SECRET not in shown.out + shown.err
    assert "created  /citedesk/prod/CITEDESK_OPENAI_API_KEY" in shown.out
    assert "kept     /citedesk/prod/CITEDESK_OPENAI_API_KEY" in shown.out
    assert shown.out.count("match") == 3
    assert read_env_file(out)["CITEDESK_OPENAI_API_KEY"] == SECRET


def test_cli_push_reports_missing_variables_and_verify_fails_on_a_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    aws = FakeAws()
    monkeypatch.setattr("citedesk.cli._store", lambda args: ParameterStore(args.path, run=aws))
    env = tmp_path / ".env"
    env.write_text("CITEDESK_OPENAI_API_KEY=abc\n")

    assert main(["ssm", "push", "--env-file", str(env)]) == 1
    assert "not set in" in capsys.readouterr().err
    assert aws.parameters == {}  # nothing is stored when anything is missing

    assert main(["ssm", "push", "--env-file", str(env), "--only", "CITEDESK_OPENAI_API_KEY"]) == 0
    env.write_text("CITEDESK_OPENAI_API_KEY=changed\n")
    assert main(["ssm", "verify", "--env-file", str(env), "--only", "CITEDESK_OPENAI_API_KEY"]) == 1
    assert "DIFFERENT" in capsys.readouterr().out


def test_cli_can_store_a_freshly_generated_signing_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    aws = FakeAws()
    monkeypatch.setattr("citedesk.cli._store", lambda args: ParameterStore(args.path, run=aws))
    env = tmp_path / ".env"
    env.write_text("CITEDESK_OPENAI_API_KEY=abc\n")
    assert (
        main(
            [
                "ssm",
                "push",
                "--env-file",
                str(env),
                "--only",
                "CITEDESK_OPENAI_API_KEY",
                "--generate-jwt-secret",
            ]
        )
        == 0
    )
    generated = str(aws.parameters[f"{DEFAULT_PATH}CITEDESK_JWT_DEV_SECRET"]["Value"])
    assert len(generated) >= 48
    assert generated not in capsys.readouterr().out


def test_cli_reports_a_missing_env_file_without_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["ssm", "push", "--env-file", "/nonexistent/.env"]) == 1
    assert "Error" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("variable", "expected"),
    [
        ("CITEDESK_OPENAI_API_KEY", "SecureString"),
        ("CITEDESK_PINECONE_API_KEY", "SecureString"),
        ("CITEDESK_JWT_DEV_SECRET", "SecureString"),
        ("CITEDESK_LOCAL_DB_PASSWORD", "SecureString"),
        ("CITEDESK_DATABASE_URL", "SecureString"),
        ("CITEDESK_OPENAI_MODEL", "String"),
        ("CITEDESK_WRITER", "String"),
        ("CITEDESK_OPENAI_MAX_OUTPUT_TOKENS", "String"),  # "TOKENS" is a count, not a token
    ],
)
def test_secrets_are_encrypted_and_plain_settings_are_readable(
    variable: str, expected: str
) -> None:
    assert parameter_type(variable) == expected


def test_a_plain_setting_is_stored_as_a_string_parameter(
    store: ParameterStore, aws: FakeAws
) -> None:
    store.push({"CITEDESK_OPENAI_MODEL": "gpt-5.4-nano", "CITEDESK_OPENAI_API_KEY": SECRET})
    assert aws.parameters[f"{PATH}CITEDESK_OPENAI_MODEL"]["Type"] == "String"
    assert aws.parameters[f"{PATH}CITEDESK_OPENAI_API_KEY"]["Type"] == "SecureString"
