"""Application settings, read from environment variables prefixed with CITEDESK_."""

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ModelBackend = Literal["offline", "local"]
WriterKind = Literal["extractive", "openai"]

# Relevance thresholds only mean something for the reranker they were calibrated on.
OFFLINE_MIN_RELEVANCE = 0.5
# Calibrated with `citedesk eval-retrieval --models local` on the sample handbook: the strongest
# unanswerable question scored -10.72 and the weakest answerable ones -10.6 and -10.9. -10.0 refuses
# every known unanswerable question and costs the two hardest paraphrases. Only 6 unanswerable
# questions were used, so re-check on a real handbook.
LOCAL_MIN_RELEVANCE = -10.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CITEDESK_", env_file=".env", extra="ignore")

    # SQLite works out of the box; use a Postgres URL such as
    # postgresql+psycopg://user:password@host/db when deploying.
    database_url: str = "sqlite:///citedesk.local.db"

    # Retrieval sizes (see docs/architecture/technical-architecture.md).
    candidate_limit: int = 20
    rerank_pool: int = 30
    final_passage_limit: int = 6

    # "offline": word-matching stand-ins, no downloads. "local": real embedding model and
    # cross-encoder on this machine (needs `uv sync --extra models`).
    models: ModelBackend = "offline"

    # Who writes the answer text. "extractive" quotes the best sentence (no model, no key). "openai"
    # asks a language model, which can combine passages, and needs CITEDESK_OPENAI_API_KEY.
    writer: WriterKind = "extractive"
    openai_api_key: SecretStr | None = None  # never printed: SecretStr hides it in logs and repr
    # Chosen by measurement (see docs/evaluation): nearly the same quality as gpt-5.4-mini on the
    # sample questions at a lower price. Change it with CITEDESK_OPENAI_MODEL.
    openai_model: str = "gpt-5.4-nano"
    openai_max_output_tokens: int = 400
    openai_timeout_seconds: float = 30.0

    # Passages scoring below this relevance after reranking are dropped, so the assistant
    # refuses instead of answering from unrelated text. Leave unset to use the calibrated
    # default for the chosen `models` backend.
    min_relevance: float | None = None

    # Chunking.
    chunk_max_chars: int = 1200
    min_document_chars: int = 100

    # --- web API ---
    # Secret used to sign and check sign-in tokens in local development. The API refuses to
    # start without it. In production, sign-in tokens should come from an OIDC provider (planned).
    jwt_dev_secret: str | None = None
    # Browser origins allowed to call the API (the web app).
    cors_origins: list[str] = ["http://localhost:3000"]
    # Serve the interactive API documentation at /docs (leave off in production).
    enable_api_docs: bool = False
    # Questions and admin actions allowed per signed-in user per minute.
    rate_limit_per_minute: int = 30

    # How many times the writer may try before the assistant refuses.
    max_answer_attempts: int = 2

    @property
    def relevance_threshold(self) -> float:
        if self.min_relevance is not None:
            return self.min_relevance
        return LOCAL_MIN_RELEVANCE if self.models == "local" else OFFLINE_MIN_RELEVANCE
