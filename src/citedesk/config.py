"""Application settings, read from environment variables prefixed with CITEDESK_."""

import os
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ModelBackend = Literal["offline", "local"]
WriterKind = Literal["extractive", "openai"]
VectorIndexKind = Literal["memory", "pinecone"]

# Relevance thresholds only mean something for the reranker they were calibrated on.
OFFLINE_MIN_RELEVANCE = 0.5
# Calibrated with `citedesk eval-retrieval --models local` on the sample handbook: the strongest
# unanswerable question scored -10.72 and the weakest answerable ones -10.6 and -10.9. -10.0 refuses
# every known unanswerable question and costs the two hardest paraphrases. Only 6 unanswerable
# questions were used, so re-check on a real handbook.
LOCAL_MIN_RELEVANCE = -10.0


class Settings(BaseSettings):
    # Settings come from CITEDESK_* environment variables first, then from the file named by
    # CITEDESK_ENV_FILE (default ".env"). Set CITEDESK_ENV_FILE=/dev/null to ignore every file,
    # which is what throwaway test servers do so they can never pick up real keys or services.
    model_config = SettingsConfigDict(
        env_prefix="CITEDESK_",
        env_file=os.environ.get("CITEDESK_ENV_FILE", ".env"),
        extra="ignore",
    )

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

    # Names this deployment, for example "dev" or "prod". It labels traces and, unless set
    # explicitly, names the Pinecone namespace so environments never share vectors.
    environment: str = "dev"

    # Tracing of each answer in LangSmith. OFF by default: traces contain the question and, unless
    # hidden, the handbook passages. See src/citedesk/tracing.py.
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "cite-desk"
    langsmith_hide_content: bool = False

    # Where vectors are kept. "memory" forgets them when the process stops (they are rebuilt from
    # the database at start). "pinecone" keeps them in a Pinecone serverless index.
    vector_index: VectorIndexKind = "memory"
    pinecone_api_key: SecretStr | None = None
    pinecone_index: str = "cite-desk"
    # One namespace per environment, so development and production never see each other's vectors.
    # Leave unset to use CITEDESK_ENVIRONMENT.
    pinecone_namespace: str | None = None
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"  # the region available on Pinecone's free plan

    # Who writes the answer text. "extractive" quotes the best sentence (no model, no key). "openai"
    # asks a language model, which can combine passages, and needs CITEDESK_OPENAI_API_KEY.
    writer: WriterKind = "extractive"
    openai_api_key: SecretStr | None = None  # never printed: SecretStr hides it in logs and repr
    # Chosen by measurement (see docs/evaluation): nearly the same quality as gpt-5.4-mini on the
    # sample questions at a lower price. Change it with CITEDESK_OPENAI_MODEL.
    openai_model: str = "gpt-5.4-nano"
    openai_max_output_tokens: int = 400
    openai_timeout_seconds: float = 30.0

    # Verified answers are remembered in memory (0 turns the cache off).
    answer_cache_size: int = 500
    answer_cache_ttl_seconds: int = 3600

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

    @property
    def vector_namespace(self) -> str:
        return self.pinecone_namespace or self.environment
