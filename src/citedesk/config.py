"""Application settings, read from environment variables prefixed with CITEDESK_."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CITEDESK_", env_file=".env", extra="ignore")

    # SQLite works out of the box; use a Postgres URL such as
    # postgresql+psycopg://user:password@host/db when deploying.
    database_url: str = "sqlite:///citedesk.local.db"

    # Retrieval sizes (see docs/architecture/technical-architecture.md).
    candidate_limit: int = 20
    rerank_pool: int = 30
    final_passage_limit: int = 6

    # Passages scoring below this relevance after reranking are dropped, so the
    # assistant refuses instead of answering from unrelated text.
    min_relevance: float = 0.5

    # Chunking.
    chunk_max_chars: int = 1200
    min_document_chars: int = 100

    # How many times the writer may try before the assistant refuses.
    max_answer_attempts: int = 2
