"""Command line for trying CiteDesk locally.

citedesk add handbook.md --title "Handbook" --license "CC BY 4.0" --publish
citedesk ask "How many vacation days do I get?"
citedesk list
"""

import argparse
import sys
from pathlib import Path

from citedesk.bootstrap import build_app
from citedesk.ingestion.parsing import ContentType, ParseError
from citedesk.ingestion.service import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    PublishBlockedError,
)

_ACTOR = "cli"
_CONTENT_TYPES: dict[str, ContentType] = {".md": "markdown", ".html": "html", ".htm": "html"}


def main(argv: list[str] | None = None) -> int:
    """Run one command. Expected problems print a short message and return 1."""
    try:
        return _run(argv)
    except (
        DuplicateDocumentError,
        PublishBlockedError,
        ParseError,
        DocumentNotFoundError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def _run(argv: list[str] | None) -> int:
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

    args = parser.parse_args(argv)
    app = build_app()

    if args.command == "add":
        content_type = _CONTENT_TYPES.get(args.path.suffix.lower(), "text")
        document = app.ingestion.add_text(
            args.path.read_text(encoding="utf-8"),
            content_type=content_type,
            title=args.title,
            source_name=args.source,
            actor=_ACTOR,
            license=args.license,
        )
        chunk_count = len(app.ingestion.preview(document.id))
        print(f"Added {document.id} ({chunk_count} chunks, draft)")
        if args.publish:
            app.ingestion.publish(document.id, actor=_ACTOR)
            print("Published")
    elif args.command == "publish":
        app.ingestion.publish(args.document_id, actor=_ACTOR)
        print("Published")
    elif args.command == "unpublish":
        app.ingestion.unpublish(args.document_id, actor=_ACTOR)
        print("Unpublished")
    elif args.command == "list":
        for document in app.repository.list_documents():
            print(f"{document.id}  {document.status.value:<9}  {document.title}")
    elif args.command == "ask":
        answer = app.answers.ask(args.question)
        if answer.refused:
            print(f"I can't answer that from the handbook ({answer.refusal_reason}).")
        else:
            print(answer.text)
            for citation in answer.citations:
                print(f"  [{citation.marker}] {citation.document_title} > {citation.section_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
