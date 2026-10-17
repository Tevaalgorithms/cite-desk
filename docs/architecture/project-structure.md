# CiteDesk — Project Structure

```text
cite-desk/
  apps/web/                 Next.js: chat, admin console, quality dashboard
  src/citedesk/
    api/                    FastAPI routes, auth, rate limits, streaming
    ingestion/              sources, fetchers, parsers, chunking, provenance
    retrieval/              BM25, Pinecone store, fusion (RRF), reranker
    agents/                 LangGraph answer flow, router, step budget
    citations/              verifier and answer formatter
    llm/                    model and embedding adapters
    evaluation/             RAGAS and DeepEval runners, thresholds, reports
    db/                     schema and migrations
  tests/                    unit and integration tests, deterministic fixtures
  evals/                    golden sets, thresholds.yaml, baselines, reports
  infrastructure/           docker, terraform
  .github/workflows/        ci.yml, eval-pr.yml, eval-nightly.yml, deploy.yml
  docs/                     product, architecture, evaluation, implementation
  schemas/                  example manifests and eval cases
```

Only the documentation and schemas exist today; code folders are added phase by phase per the roadmap.

## Dependency rules

- `retrieval` never imports `agents`, `citations` or `api`.
- `citations` never imports `retrieval`; it receives passages as input.
- `agents` composes `retrieval`, `citations` and `llm`; nothing imports `agents` except `api`.
- `ingestion` writes through `db` and the retrieval index interfaces; it never imports `agents`.
- `evaluation` may import any module but is never imported by the application.
- Retrievers, LLMs, vector store and cache sit behind interfaces so providers stay swappable.

These rules are enforced by a test that inspects imports, once code exists.

## Standards

- Python 3.12 with `uv` and a committed lockfile; Ruff, strict mypy and pytest with coverage; TypeScript strict, ESLint and Vitest on the web app.
- Conventional commits, protected `main`, a pull request template, and CODEOWNERS.
- Architecture decision records for every deviation; each source or threshold change is a reviewed commit.
- gitleaks, pip-audit and npm audit gate every pull request.
