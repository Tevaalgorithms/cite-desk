"""Command line for trying CiteDesk locally.

citedesk add handbook.md --title "Handbook" --license "CC BY 4.0" --publish
citedesk ask "How many vacation days do I get?"
citedesk list
citedesk eval-retrieval --models local --check evals/baselines.json
"""

import argparse
import json
import sys
from pathlib import Path

from citedesk.api.auth import issue_token
from citedesk.bootstrap import App, build_app
from citedesk.config import Settings
from citedesk.evaluation.gates import check_gates, load_baseline
from citedesk.evaluation.runner import format_report, run_evaluation, summarize
from citedesk.ingestion.parsing import ContentType, ParseError
from citedesk.ingestion.service import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    PublishBlockedError,
)

_ACTOR = "cli"
_CONTENT_TYPES: dict[str, ContentType] = {".md": "markdown", ".html": "html", ".htm": "html"}
_EXPECTED_ERRORS = (DuplicateDocumentError, PublishBlockedError, ParseError, DocumentNotFoundError)


def main(argv: list[str] | None = None) -> int:
    """Run one command. Expected problems print a short message and return 1."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "eval-retrieval":
            return _eval_retrieval(args)  # builds its own throwaway app
        if args.command == "token":
            return _token(args)
        if args.command == "serve":
            return _serve(args)
        return _COMMANDS[args.command](build_app(), args)
    except _EXPECTED_ERRORS as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


# --- commands that work on the local database ---------------------------------------------


def _add(app: App, args: argparse.Namespace) -> int:
    document = app.ingestion.add_text(
        args.path.read_text(encoding="utf-8"),
        content_type=_CONTENT_TYPES.get(args.path.suffix.lower(), "text"),
        title=args.title,
        source_name=args.source,
        actor=_ACTOR,
        license=args.license,
    )
    print(f"Added {document.id} ({len(app.ingestion.preview(document.id))} chunks, draft)")
    if args.publish:
        app.ingestion.publish(document.id, actor=_ACTOR)
        print("Published")
    return 0


def _publish(app: App, args: argparse.Namespace) -> int:
    app.ingestion.publish(args.document_id, actor=_ACTOR)
    print("Published")
    return 0


def _unpublish(app: App, args: argparse.Namespace) -> int:
    app.ingestion.unpublish(args.document_id, actor=_ACTOR)
    print("Unpublished")
    return 0


def _list(app: App, args: argparse.Namespace) -> int:
    for document in app.repository.list_documents():
        print(f"{document.id}  {document.status.value:<9}  {document.title}")
    return 0


def _ask(app: App, args: argparse.Namespace) -> int:
    answer = app.answers.ask(args.question)
    if answer.refused:
        print(f"I can't answer that from the handbook ({answer.refusal_reason}).")
        return 0
    print(answer.text)
    for citation in answer.citations:
        print(f"  [{citation.marker}] {citation.document_title} > {citation.section_path}")
    return 0


_COMMANDS = {
    "add": _add,
    "publish": _publish,
    "unpublish": _unpublish,
    "list": _list,
    "ask": _ask,
}


# --- web API ------------------------------------------------------------------------------


def _token(args: argparse.Namespace) -> int:
    """Print a sign-in token for local development. The signing secret is never printed."""
    secret = Settings().jwt_dev_secret
    if not secret:
        print("Error: set CITEDESK_JWT_DEV_SECRET first.", file=sys.stderr)
        return 1
    print(issue_token(secret, args.user, args.role, ttl_seconds=args.hours * 3600))
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "citedesk.api.main:create_production_app", factory=True, host=args.host, port=args.port
    )
    return 0


# --- evaluation ---------------------------------------------------------------------------


def _eval_retrieval(args: argparse.Namespace) -> int:
    retrieval, suggestion, answers, threshold, _ = run_evaluation(
        args.models, args.handbook, args.golden
    )
    summary = summarize(retrieval, answers)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_report(args.models, retrieval, suggestion, answers, threshold))
    if args.check is None:
        return 0

    failures = check_gates(summary, load_baseline(args.check, args.models, args.golden.stem))
    for failure in failures:
        print(f"GATE FAILED: {failure}", file=sys.stderr)
    print("Quality gates: " + ("FAILED" if failures else "passed"))
    return 1 if failures else 0


# --- argument parsing ---------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citedesk")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="add a local file as a draft document")
    add.add_argument("path", type=Path)
    add.add_argument("--title", required=True)
    add.add_argument("--source", default="local file")
    add.add_argument("--license", default=None)
    add.add_argument("--publish", action="store_true", help="publish right after adding")

    publish = commands.add_parser("publish", help="publish a draft document")
    publish.add_argument("document_id")

    unpublish = commands.add_parser("unpublish", help="take a document out of search")
    unpublish.add_argument("document_id")

    ask = commands.add_parser("ask", help="ask a question")
    ask.add_argument("question")

    commands.add_parser("list", help="list documents")

    token = commands.add_parser("token", help="print a development sign-in token")
    token.add_argument("--user", required=True)
    token.add_argument("--role", choices=["analyst", "reviewer", "admin"], default="analyst")
    token.add_argument("--hours", type=int, default=8)

    serve = commands.add_parser("serve", help="run the web API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    evaluate = commands.add_parser(
        "eval-retrieval", help="measure retrieval and answers on the sample handbook"
    )
    evaluate.add_argument("--models", choices=["offline", "local"], default="offline")
    evaluate.add_argument("--handbook", type=Path, default=Path("data/sample/acme-handbook.md"))
    evaluate.add_argument("--golden", type=Path, default=Path("evals/sample/golden.json"))
    evaluate.add_argument("--json", action="store_true", help="print only the gate numbers as JSON")
    evaluate.add_argument(
        "--check",
        type=Path,
        metavar="BASELINES",
        help="compare with a baselines file and exit 1 if anything got worse",
    )
    return parser


if __name__ == "__main__":
    sys.exit(main())
