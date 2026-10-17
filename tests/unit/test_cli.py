from pathlib import Path

import pytest

from citedesk.cli import main
from tests.conftest import SAMPLE_HANDBOOK


@pytest.fixture(autouse=True)
def _local_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CITEDESK_DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")


def test_add_publish_ask_and_list_work_together(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    handbook = tmp_path / "handbook.md"
    handbook.write_text(SAMPLE_HANDBOOK)

    assert main(["add", str(handbook), "--title", "Acme", "--license", "CC0", "--publish"]) == 0
    assert main(["ask", "How many vacation days do I get?"]) == 0
    assert main(["list"]) == 0

    output = capsys.readouterr().out
    assert "Published" in output
    assert "20 days" in output
    assert "Time off > Vacation" in output
    assert "published" in output


def test_ask_says_so_when_nothing_is_published(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ask", "What is the capital of France?"]) == 0
    assert "can't answer" in capsys.readouterr().out


def test_expected_problems_print_a_short_error_instead_of_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    handbook = tmp_path / "handbook.md"
    handbook.write_text(SAMPLE_HANDBOOK)

    assert main(["add", str(handbook), "--title", "Acme"]) == 0  # no license: stays a draft
    document_id = capsys.readouterr().out.split()[1]

    assert main(["publish", document_id]) == 1  # blocked: no license
    assert main(["add", str(handbook), "--title", "Acme", "--license", "CC0"]) == 1  # duplicate
    assert main(["publish", "does-not-exist"]) == 1

    errors = capsys.readouterr().err
    assert "license" in errors
    assert "Same content already added" in errors
    assert "Traceback" not in errors
