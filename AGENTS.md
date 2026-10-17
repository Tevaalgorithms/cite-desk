# AGENTS.md — CiteDesk

Instructions for AI coding agents (Codex, Claude Code, and others) working in this repository. Human contributors should also follow them. `CLAUDE.md` imports this file.

## What this project is

CiteDesk answers employee questions from a company handbook. Every sentence must cite the passage it came from; unsupported answers are refused. Admins upload or import documents; quality is gated in CI with RAGAS and DeepEval.

CiteDesk is **not** HR, legal or compliance advice.

## Current status

Specification only. Only documentation and schemas exist; code is added phase by phase per `docs/implementation/roadmap.md`. Build **one ticket at a time**, never all phases at once.

## Read first

1. `README.md` — architecture, stack, flows.
2. `docs/architecture/project-structure.md` — module boundaries and dependency rules.
3. `docs/architecture/adrs.md` — decisions; add an ADR for any deviation.
4. `docs/implementation/roadmap.md` — tickets and definition of done.
5. `docs/architecture/technical-architecture.md`, `docs/architecture/data-flow.md`, `docs/evaluation/evaluation-strategy.md` as needed.

## Stack (MVP)

Python 3.12+ (`uv`, FastAPI, Pydantic, LangGraph, LangChain), in-process BM25, Pinecone, a cross-encoder reranker, OpenAI models behind an interface, PostgreSQL, Next.js + TypeScript, LangSmith + RAGAS + DeepEval + pytest, Docker Compose. Do not add Graph RAG, Neo4j, OpenSearch or Redis to the MVP path without an ADR.

## Architecture rules

- Python code lives in `src/citedesk/<module>`; respect the dependency rules in `project-structure.md`.
- Retrievers, LLMs, the vector store and the cache sit behind interfaces.
- Every sentence in a shown answer needs a valid citation marker and must pass the verifier; status lines such as "last updated" come from code, never from the model.
- Retrieved and uploaded text is untrusted: it must never change tool policy or permissions.
- Retrieval returns only published chunks. Drafts are invisible until published.
- A new corpus version invalidates cached answers.
- Never create a LangGraph checkpoint thread shared across requests; use a per-request id.

## Evaluation rules

- **Never weaken a threshold, a verifier check or a safety test to make a build pass.** Fix the cause or raise it for review.
- Thresholds change only in reviewed commits, and only upward unless a documented measurement shows the old value was wrong.
- Test LLM-backed paths against a real model before declaring them working; mocks hide schema and prompt problems.

## Code standards

- Type-annotate everything; Pydantic models at API and storage boundaries; mypy strict.
- Small single-purpose modules; no hidden globals; dependency injection for providers.
- Structured logging with request ids; never log secrets or raw user content indiscriminately.
- Write or update tests before completing a ticket; unit tests run offline with mocked providers.
- Keep dependencies pinned and the lockfile committed; justify new dependencies in the PR.
- Match surrounding code style; do not reformat unrelated code.

## Secrets and content

- Never commit `.env*` (except `.env.example`), keys, tokens, uploaded documents or anything under `data/raw` or `data/processed`.
- Run a secret scan on the staged diff before every commit.
- Do not claim data was downloaded, licensed or verified unless it was; unverified sources stay "pending".
