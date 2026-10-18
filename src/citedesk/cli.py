"""Command line for trying CiteDesk locally.

citedesk add handbook.md --title "Handbook" --license "CC BY 4.0" --publish
citedesk ask "How many vacation days do I get?"
citedesk list
citedesk eval-retrieval --models local --check evals/baselines.json
"""

import argparse
import json
import secrets
import sys
from pathlib import Path
from typing import Any

from citedesk.api.auth import issue_token
from citedesk.bootstrap import App, build_app, build_index, build_models
from citedesk.config import Settings
from citedesk.evaluation.gates import check_gates, load_baseline
from citedesk.evaluation.runner import format_report, run_evaluation, summarize
from citedesk.indexing import sync_vector_index
from citedesk.ingestion.parsing import ContentType, ParseError
from citedesk.ingestion.service import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    InvalidDocumentError,
    PublishBlockedError,
)
from citedesk.ops.ssm import (
    DEFAULT_PATH,
    DEFAULT_SECRETS,
    ParameterStore,
    SsmError,
    read_env_file,
)
from citedesk.storage.repository import SqlRepository

_ACTOR = "cli"
_CONTENT_TYPES: dict[str, ContentType] = {".md": "markdown", ".html": "html", ".htm": "html"}
_EXPECTED_ERRORS = (
    DuplicateDocumentError,
    PublishBlockedError,
    ParseError,
    DocumentNotFoundError,
    InvalidDocumentError,
    SsmError,
    FileNotFoundError,
)


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
        if args.command == "ssm":
            return _ssm(args)
        if args.command == "pinecone":
            return _pinecone(args)
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


def _license(app: App, args: argparse.Namespace) -> int:
    app.ingestion.set_license(args.document_id, args.license, actor=_ACTOR)
    print("License recorded")
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
    app.tracer.flush()  # a short-lived command must send its traces before it exits
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
    "license": _license,
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


# --- Pinecone vector index -----------------------------------------------------------------


def _pinecone(args: argparse.Namespace) -> int:
    """Create, inspect or repair the Pinecone index. Uses CITEDESK_PINECONE_* settings."""
    settings = Settings().model_copy(update={"vector_index": "pinecone"})
    embedder, _ = build_models(settings)
    index = build_index(settings, embedder)  # creates the index on first use
    repository = SqlRepository.from_url(settings.database_url)
    where = f"{settings.pinecone_index} / namespace {settings.vector_namespace}"

    if args.pinecone_command == "init":
        print(f"Index ready: {where} ({embedder.dimension} numbers per vector, cosine)")
        return 0

    if args.pinecone_command == "sync":
        report = sync_vector_index(repository, embedder, index)
        print(
            f"{where}: {report.published} published, {report.added} added, {report.removed} removed"
        )
        return 0

    wanted = {p.chunk_id for p in repository.published_passages()}
    stored = index.ids()
    print(f"{where}")
    print(f"  vectors stored    : {len(stored)}")
    print(f"  chunks published  : {len(wanted)}")
    print(f"  missing from index: {len(wanted - stored)}")
    print(f"  extra in index    : {len(stored - wanted)}")
    in_sync = stored == wanted
    print("  in sync           : " + ("yes" if in_sync else "NO (run `citedesk pinecone sync`)"))
    return 0 if in_sync else 1


# --- production secrets in AWS SSM Parameter Store ------------------------------------------


def _store(args: argparse.Namespace) -> ParameterStore:
    return ParameterStore(args.path)


def _ssm(args: argparse.Namespace) -> int:
    """Manage production secrets. Values are never printed."""
    store = _store(args)
    only = getattr(args, "only", None)  # not every ssm command has --only
    names = tuple(only) if only else DEFAULT_SECRETS

    if args.ssm_command == "push":
        local = read_env_file(args.env_file)
        values = {name: local.get(name, "") for name in names}
        if args.generate_jwt_secret:
            values["CITEDESK_JWT_DEV_SECRET"] = secrets.token_urlsafe(48)
        missing = [name for name, value in values.items() if not value]
        if missing:
            print(f"Error: not set in {args.env_file}: {', '.join(missing)}", file=sys.stderr)
            return 1
        for name, outcome in store.push(values, overwrite=args.overwrite).items():
            print(f"{outcome:<8} {store.parameter_name(name)}")
        return 0

    if args.ssm_command == "list":
        infos = store.list_parameters()
        for info in infos:
            print(f"{info.name}  {info.type}  version {info.version}  {info.last_modified}")
        if not infos:
            print(f"Nothing stored under {args.path}")
        return 0

    if args.ssm_command == "verify":
        local = read_env_file(args.env_file)
        report = store.verify({name: local[name] for name in names if local.get(name)})
        for name, state in report.items():
            print(f"{state:<14} {name}")
        return 0 if report and all(state == "match" for state in report.values()) else 1

    written = store.write_env_file(args.out, only=only or None)
    print(f"Wrote {len(written)} setting(s) to {args.out} (owner-only file): {', '.join(written)}")
    return 0


# --- evaluation ---------------------------------------------------------------------------


def _eval_retrieval(args: argparse.Namespace) -> int:
    overrides: dict[str, Any] = {}
    if args.writer:
        overrides["writer"] = args.writer
    if args.openai_model:
        overrides["openai_model"] = args.openai_model
    run = run_evaluation(args.models, args.handbook, args.golden, **overrides)
    summary = summarize(run.retrieval, run.answers, run.coverage)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_report(args.models, run))
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

    license_ = commands.add_parser("license", help="record or correct a document's license")
    license_.add_argument("document_id")
    license_.add_argument("license")

    unpublish = commands.add_parser("unpublish", help="take a document out of search")
    unpublish.add_argument("document_id")

    ask = commands.add_parser("ask", help="ask a question")
    ask.add_argument("question")

    commands.add_parser("list", help="list documents")

    ssm = commands.add_parser("ssm", help="manage production secrets in AWS SSM Parameter Store")
    ssm.add_argument(
        "--path", default=DEFAULT_PATH, help=f"parameter path (default {DEFAULT_PATH})"
    )
    ssm_commands = ssm.add_subparsers(dest="ssm_command", required=True)
    push = ssm_commands.add_parser(
        "push", help="store secrets from .env as SecureString parameters"
    )
    push.add_argument("--env-file", type=Path, default=Path(".env"))
    push.add_argument(
        "--only", nargs="+", metavar="NAME", help="variables to store (default: the three API keys)"
    )
    push.add_argument(
        "--overwrite", action="store_true", help="replace parameters that already exist"
    )
    push.add_argument(
        "--generate-jwt-secret",
        action="store_true",
        help="also store a new random sign-in signing secret",
    )
    ssm_commands.add_parser("list", help="show stored parameter names and versions (no values)")
    verify = ssm_commands.add_parser(
        "verify", help="check stored values match .env, by fingerprint"
    )
    verify.add_argument("--env-file", type=Path, default=Path(".env"))
    verify.add_argument("--only", nargs="+", metavar="NAME")
    pull = ssm_commands.add_parser(
        "pull", help="write stored values to an owner-only settings file"
    )
    pull.add_argument("--out", type=Path, required=True)
    pull.add_argument("--only", nargs="+", metavar="NAME")

    pinecone = commands.add_parser("pinecone", help="manage the Pinecone vector index")
    pinecone_commands = pinecone.add_subparsers(dest="pinecone_command", required=True)
    pinecone_commands.add_parser("init", help="create the index if it does not exist")
    pinecone_commands.add_parser("status", help="compare the index with the published chunks")
    pinecone_commands.add_parser("sync", help="repair the index so it matches the database")

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
    evaluate.add_argument(
        "--writer", choices=["extractive", "openai"], help="answer writer to test"
    )
    evaluate.add_argument("--openai-model", help="OpenAI model to test (with --writer openai)")
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
