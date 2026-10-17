"""HTTP routes: questions for everyone signed in, document management for admins."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from citedesk.api.auth import Principal, require_roles
from citedesk.api.ratelimit import enforce
from citedesk.api.schemas import AddDocumentRequest, ChatRequest, ImportUrlRequest
from citedesk.bootstrap import App
from citedesk.domain.models import Answer, AuditEntry, Chunk, Document, Passage

router = APIRouter()

AnyUser = Annotated[Principal, Depends(require_roles("analyst", "reviewer", "admin"))]
Admin = Annotated[Principal, Depends(require_roles("admin"))]


def _app(request: Request) -> App:
    app: App = request.app.state.citedesk
    return app


# --- open endpoints -----------------------------------------------------------------------


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> dict[str, int | str]:
    """Ready when the database answers."""
    return {"status": "ready", "corpus_version": _app(request).repository.corpus_version()}


# --- questions ----------------------------------------------------------------------------


@router.post("/v1/chat")
def chat(body: ChatRequest, request: Request, principal: AnyUser) -> Answer:
    enforce(request, principal)
    return _app(request).answers.ask(body.question)


@router.get("/v1/chunks/{chunk_id}")
def get_chunk(chunk_id: str, request: Request, principal: AnyUser) -> Passage:
    """The passage behind a citation. Draft and retired documents are never served."""
    enforce(request, principal)
    passage = _app(request).answers.source_passage(chunk_id)
    if passage is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such passage")
    return passage


# --- admin: documents ---------------------------------------------------------------------


@router.get("/v1/admin/documents")
def list_documents(request: Request, principal: Admin) -> list[Document]:
    enforce(request, principal)
    return _app(request).repository.list_documents()


@router.post("/v1/admin/documents", status_code=status.HTTP_201_CREATED)
def add_document(body: AddDocumentRequest, request: Request, principal: Admin) -> Document:
    enforce(request, principal)
    return _app(request).ingestion.add_text(
        body.content,
        content_type=body.content_type,
        title=body.title,
        source_name=body.source_name,
        actor=principal.user_id,
        license=body.license,
        terms_url=body.terms_url,
    )


@router.post("/v1/admin/imports", status_code=status.HTTP_201_CREATED)
def import_url(body: ImportUrlRequest, request: Request, principal: Admin) -> Document:
    enforce(request, principal)
    return _app(request).ingestion.add_url(
        body.url,
        source_name=body.source_name,
        actor=principal.user_id,
        license=body.license,
        terms_url=body.terms_url,
    )


@router.get("/v1/admin/documents/{document_id}/preview")
def preview_document(document_id: str, request: Request, principal: Admin) -> list[Chunk]:
    enforce(request, principal)
    return _app(request).ingestion.preview(document_id)


@router.post("/v1/admin/documents/{document_id}/publish")
def publish_document(document_id: str, request: Request, principal: Admin) -> Document:
    enforce(request, principal)
    return _app(request).ingestion.publish(document_id, actor=principal.user_id)


@router.post("/v1/admin/documents/{document_id}/unpublish")
def unpublish_document(document_id: str, request: Request, principal: Admin) -> Document:
    enforce(request, principal)
    return _app(request).ingestion.unpublish(document_id, actor=principal.user_id)


@router.get("/v1/admin/audit")
def audit_log(request: Request, principal: Admin, limit: int = 100) -> list[AuditEntry]:
    enforce(request, principal)
    return _app(request).repository.audit_log(limit=min(max(limit, 1), 500))
