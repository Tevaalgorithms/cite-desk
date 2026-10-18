"""Keep the two halves of the system apart (see docs/architecture/project-structure.md)."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "citedesk"


def _imports_in(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def _imported_modules(folder: str) -> set[str]:
    modules: set[str] = set()
    for path in (PACKAGE / folder).glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
    return modules


def _violations(folder: str, forbidden: tuple[str, ...]) -> list[str]:
    return sorted(m for m in _imported_modules(folder) if m.startswith(forbidden))


def test_ingestion_does_not_depend_on_the_answer_flow_or_a_concrete_database() -> None:
    assert (
        _violations("ingestion", ("citedesk.answer", "citedesk.storage", "citedesk.bootstrap"))
        == []
    )


def test_the_answer_flow_does_not_depend_on_ingestion_or_a_concrete_database() -> None:
    assert (
        _violations("answer", ("citedesk.ingestion", "citedesk.storage", "citedesk.bootstrap"))
        == []
    )


def test_the_shared_domain_depends_on_neither_side() -> None:
    forbidden = ("citedesk.answer", "citedesk.ingestion", "citedesk.storage", "citedesk.bootstrap")
    assert _violations("domain", forbidden) == []


def test_storage_depends_only_on_the_domain() -> None:
    assert (
        _violations("storage", ("citedesk.answer", "citedesk.ingestion", "citedesk.bootstrap"))
        == []
    )


def test_real_service_adapters_are_wired_in_only_by_bootstrap() -> None:
    """Everything else depends on the interfaces, so a vendor can be replaced in one place."""
    importers = []
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE)
        if relative.parts[0] == "adapters" or relative.name == "bootstrap.py":
            continue
        if any(m.startswith("citedesk.adapters") for m in _imports_in(path)):
            importers.append(str(relative))
    assert importers == []
