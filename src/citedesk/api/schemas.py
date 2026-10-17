"""Request bodies. Limits here protect the server from oversized input."""

from pydantic import BaseModel, Field

from citedesk.ingestion.parsing import ContentType


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AddDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=2_000_000)
    content_type: ContentType = "markdown"
    source_name: str = Field(min_length=1, max_length=300)
    license: str | None = Field(default=None, max_length=300)
    terms_url: str | None = Field(default=None, max_length=2000)


class ImportUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    source_name: str = Field(min_length=1, max_length=300)
    license: str | None = Field(default=None, max_length=300)
    terms_url: str | None = Field(default=None, max_length=2000)
