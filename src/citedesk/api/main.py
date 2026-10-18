"""Builds the web application.

Run locally with:
    export CITEDESK_JWT_DEV_SECRET=<long random text>
    uv run uvicorn citedesk.api.main:create_production_app --factory
"""

import logging
import uuid

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from citedesk.api.ratelimit import RateLimiter
from citedesk.api.routes import router
from citedesk.bootstrap import App, build_app
from citedesk.config import Settings
from citedesk.ingestion.fetching import FetchError, UnsafeUrlError
from citedesk.ingestion.parsing import ParseError
from citedesk.ingestion.service import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    InvalidDocumentError,
    PublishBlockedError,
)

logger = logging.getLogger("citedesk.api")

# Expected problems become short, safe messages. Anything else is a 500 with no details.
_ERROR_STATUS: list[tuple[type[Exception], int]] = [
    (DocumentNotFoundError, status.HTTP_404_NOT_FOUND),
    (DuplicateDocumentError, status.HTTP_409_CONFLICT),
    (PublishBlockedError, status.HTTP_409_CONFLICT),
    (ParseError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (InvalidDocumentError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (UnsafeUrlError, status.HTTP_400_BAD_REQUEST),
    (FetchError, status.HTTP_502_BAD_GATEWAY),
]


def create_api(citedesk: App, settings: Settings) -> FastAPI:
    """Wrap an already built `App` in a web application."""
    if not settings.jwt_dev_secret:
        raise RuntimeError("Set CITEDESK_JWT_DEV_SECRET: the API will not start without a secret.")

    # The interactive API documentation is off unless explicitly enabled.
    docs = settings.enable_api_docs
    api = FastAPI(
        title="CiteDesk",
        version="0.1.0",
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    api.state.citedesk = citedesk
    api.state.jwt_secret = settings.jwt_dev_secret
    api.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @api.middleware("http")
    async def request_id_and_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = uuid.uuid4().hex[:12]
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    for error_type, code in _ERROR_STATUS:

        def handler(request: Request, error: Exception, code: int = code) -> JSONResponse:
            return JSONResponse(status_code=code, content={"detail": str(error)})

        api.add_exception_handler(error_type, handler)

    @api.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    api.include_router(router)
    return api


def create_production_app() -> FastAPI:
    settings = Settings()
    return create_api(build_app(settings), settings)
