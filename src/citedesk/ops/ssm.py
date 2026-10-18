"""Keep production secrets in AWS Systems Manager Parameter Store (SecureString).

Each secret is one parameter named after its environment variable, for example
`/citedesk/prod/CITEDESK_OPENAI_API_KEY`, so a whole environment can be read back by path
and written out as a settings file. Values are never printed or logged by this module, and
they are passed to the AWS command line through a private temporary file, not on the command
line where other users could see them.
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = "/citedesk/prod/"

# Secrets pushed by default. Anything else must be named explicitly with --only, so a local-only
# value (like a SQLite path) is never copied to production by accident.
DEFAULT_SECRETS = (
    "CITEDESK_OPENAI_API_KEY",
    "CITEDESK_PINECONE_API_KEY",
    "CITEDESK_LANGSMITH_API_KEY",
)

_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
# A setting is encrypted (SecureString) when its name contains one of these whole words, or it is
# listed below. Everything else, such as the model name, is stored as plain readable text.
_SECRET_WORD = re.compile(r"(^|_)(KEY|SECRET|TOKEN|PASSWORD)($|_)")
_ALWAYS_ENCRYPTED = frozenset({"CITEDESK_DATABASE_URL"})  # a connection string holds a password
_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)=(.*)$")

Runner = Callable[[Sequence[str]], "CommandResult"]


class SsmError(RuntimeError):
    """Something went wrong talking to AWS. The message never contains a secret value."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_aws(arguments: Sequence[str]) -> CommandResult:
    """Run the AWS command line. Output is captured, never echoed."""
    completed = subprocess.run(
        ["aws", *arguments], capture_output=True, text=True, check=False, timeout=60
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def parameter_type(variable: str) -> str:
    """ "SecureString" for anything secret, otherwise "String"."""
    if variable in _ALWAYS_ENCRYPTED or _SECRET_WORD.search(variable):
        return "SecureString"
    return "String"


def read_env_file(path: Path) -> dict[str, str]:
    """Read NAME=value lines. Surrounding quotes are removed; comments and blanks are skipped."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LINE.match(line)
        if match:
            value = match.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[match.group(1)] = value
    return values


def fingerprint(value: str) -> str:
    """A short, one-way fingerprint for comparing values without revealing them."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


@dataclass(frozen=True)
class ParameterInfo:
    name: str
    type: str
    version: int
    last_modified: str


class ParameterStore:
    def __init__(self, path: str = DEFAULT_PATH, run: Runner = run_aws) -> None:
        if not path.startswith("/") or not path.endswith("/"):
            raise ValueError("The parameter path must start and end with '/'")
        self._path = path
        self._run = run

    def parameter_name(self, variable: str) -> str:
        if not _NAME.match(variable):
            raise ValueError(f"{variable!r} is not an environment variable name")
        return f"{self._path}{variable}"

    def push(self, values: Mapping[str, str], *, overwrite: bool = False) -> dict[str, str]:
        """Store each value (encrypted if it is a secret). Returns variable -> "created" etc.

        Without `overwrite`, a parameter that already exists is left alone ("kept").
        """
        outcome: dict[str, str] = {}
        existing = {info.name for info in self.list_parameters()}
        for variable, value in values.items():
            name = self.parameter_name(variable)
            if not value:
                raise SsmError(f"{variable} is empty; nothing to store")
            if name in existing and not overwrite:
                outcome[variable] = "kept"
                continue
            self._put(name, value, update=name in existing, variable=variable)
            outcome[variable] = "updated" if name in existing else "created"
        return outcome

    def list_parameters(self) -> list[ParameterInfo]:
        """Names, types and versions under the path. Never returns values."""
        result = self._checked(
            [
                "ssm", "get-parameters-by-path", "--path", self._path, "--recursive",
                "--output", "json",
            ]
        )  # fmt: skip
        parameters = json.loads(result.stdout or "{}").get("Parameters", [])
        return sorted(
            (
                ParameterInfo(
                    name=item["Name"],
                    type=item["Type"],
                    version=int(item["Version"]),
                    last_modified=str(item.get("LastModifiedDate", "")),
                )
                for item in parameters
            ),
            key=lambda info: info.name,
        )

    def pull(self) -> dict[str, str]:
        """Read and decrypt every parameter under the path as variable -> value."""
        result = self._checked(
            [
                "ssm", "get-parameters-by-path", "--path", self._path, "--recursive",
                "--with-decryption", "--output", "json",
            ]
        )  # fmt: skip
        parameters = json.loads(result.stdout or "{}").get("Parameters", [])
        return {item["Name"].removeprefix(self._path): item["Value"] for item in parameters}

    def verify(self, expected: Mapping[str, str]) -> dict[str, str]:
        """Compare stored values with `expected` by fingerprint. variable -> "match" etc."""
        stored = self.pull()
        report: dict[str, str] = {}
        for variable, value in expected.items():
            if variable not in stored:
                report[variable] = "missing in SSM"
            elif fingerprint(stored[variable]) == fingerprint(value):
                report[variable] = "match"
            else:
                report[variable] = "DIFFERENT"
        return report

    def write_env_file(self, destination: Path, *, only: Sequence[str] | None = None) -> list[str]:
        """Write the stored values to a settings file that only the owner can read."""
        values = self.pull()
        if only is not None:
            values = {name: value for name, value in values.items() if name in only}
        lines = [f"{name}={_quote(value)}" for name, value in sorted(values.items())]
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + ("\n" if lines else ""))
        destination.chmod(0o600)
        return sorted(values)

    # --- helpers ---------------------------------------------------------------------------

    def _put(self, name: str, value: str, *, update: bool, variable: str) -> None:
        body = {
            "Name": name,
            "Value": value,
            "Type": parameter_type(variable),
            "Description": f"CiteDesk production setting {variable}",
            "Overwrite": update,
        }
        if not update:  # tags can only be added when a parameter is created
            body["Tags"] = [
                {"Key": "project", "Value": "citedesk"},
                {"Key": "environment", "Value": "prod"},
            ]
        # The value goes through a private temporary file (mode 0600), never the command line.
        descriptor, temp_name = tempfile.mkstemp(prefix="citedesk-ssm-", suffix=".json")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(body, handle)
            self._checked(["ssm", "put-parameter", "--cli-input-json", f"file://{temp_name}"])
        finally:
            Path(temp_name).unlink(missing_ok=True)

    def _checked(self, arguments: Sequence[str]) -> CommandResult:
        result = self._run(arguments)
        if result.returncode != 0:
            # AWS error text names the problem (for example access denied), not secret values.
            raise SsmError(
                result.stderr.strip().splitlines()[-1][:300]
                if result.stderr.strip()
                else "AWS command failed"
            )
        return result


def _quote(value: str) -> str:
    """Quote a value for a settings file only when it needs it."""
    if re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]*", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
