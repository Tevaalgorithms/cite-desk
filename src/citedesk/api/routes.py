"""HTTP routes: questions for everyone signed in, document management for admins."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from citedesk.api.auth import Principal, require_roles
from citedesk.api.ratelimit import enforce
from citedesk.api.schemas import (
    AddDocumentRequest,
    ChatRequest,
    ImportUrlRequest,
    ReplaceDocumentRequest,
    SetLicenseRequest,
)
from citedesk.bootstrap import App
from citedesk.domain.models import (
    Answer,
    AuditEntry,
    Chunk,
    Document,
    ModelHealth,
    ModelInfo,
    Passage,
    UsageSnapshot,
)

router = APIRouter()

# A recent check is reused instead of calling the model again, so neither page loads nor clicks on
# "Check connection" can run up the bill. The page asks for a result up to 5 minutes old when it
# loads; the button accepts one up to 15 seconds old (the least the server allows).
_MIN_REUSE_SECONDS = 15
_DEFAULT_REUSE_SECONDS = 300

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


# --- which model answers ---------------------------------------------------------------------


class ModelReport(BaseModel):
    """What the status bar in the web app shows."""

    info: ModelInfo
    health: ModelHealth | None  # None until the connection has been checked
    usage: UsageSnapshot | None


def _older_than(checked_at: datetime, seconds: int) -> bool:
    return (datetime.now(UTC) - checked_at).total_seconds() >= seconds


def _report(request: Request) -> ModelReport:
    status_source = _app(request).model
    health: ModelHealth | None = request.app.state.model_health
    if health is None and status_source.info().writer != "openai":
        health = status_source.check()  # the built-in writer needs no network: always known
    return ModelReport(info=status_source.info(), health=health, usage=status_source.usage())


@router.get("/v1/model")
def model_status(request: Request, principal: AnyUser) -> ModelReport:
    """Which model writes answers and whether it was last seen working. Makes no model call."""
    enforce(request, principal)
    return _report(request)


@router.post("/v1/model/check")
def check_model(
    request: Request, principal: AnyUser, max_age_seconds: int = _DEFAULT_REUSE_SECONDS
) -> ModelReport:
    """Make one tiny real request to the model, unless a recent result can be reused."""
    enforce(request, principal)
    reuse_for = min(max(max_age_seconds, _MIN_REUSE_SECONDS), 3600)
    cached: ModelHealth | None = request.app.state.model_health
    if cached is None or cached.checked_at is None or _older_than(cached.checked_at, reuse_for):
        request.app.state.model_health = _app(request).model.check()
    return _report(request)


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


@router.post("/v1/admin/documents/{document_id}/license")
def set_license(
    document_id: str, body: SetLicenseRequest, request: Request, principal: Admin
) -> Document:
    """Record or correct a document's license (for example on a draft added without one)."""
    enforce(request, principal)
    return _app(request).ingestion.set_license(
        document_id, body.license, actor=principal.user_id, terms_url=body.terms_url
    )


@router.post("/v1/admin/documents/{document_id}/replace", status_code=status.HTTP_201_CREATED)
def replace_document(
    document_id: str, body: ReplaceDocumentRequest, request: Request, principal: Admin
) -> Document:
    """Swap a published document for a new version in one step. Returns the new document."""
    enforce(request, principal)
    return _app(request).ingestion.replace_text(
        document_id,
        body.content,
        content_type=body.content_type,
        actor=principal.user_id,
        title=body.title,
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
