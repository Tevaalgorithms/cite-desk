# CiteDesk — Project Structure

```text
cite-desk/
  apps/web/                 Next.js: chat, citation chips, source drawer, admin console, AI model status bar
  src/citedesk/
    domain/                 shared data models and interfaces (ports)
    ingestion/              parsing, chunking, safe URL fetching, publish workflow
    answer/                 BM25, fusion, retrieval, cache, rerankers, writers, verifier, LangGraph flow
    adapters/               local models, OpenAI writer, Pinecone index (real services behind the ports)
    storage/                SQL repository and the in-memory stand-ins
    api/                    FastAPI routes, dev sign-in tokens and roles, rate limits
    evaluation/             retrieval and answer evaluation, multi-part coverage, thresholds, gates
    ops/                    AWS SSM secrets tooling
    indexing.py             repairs a vector index so it matches the database
    tracing.py              optional LangSmith tracing
    bootstrap.py            the only place that wires ingestion and answers together
    config.py, cli.py       settings and the command line
  tests/                    unit (default), integration (Postgres), models, and opt-in live tests
                            for OpenAI (llm), Pinecone (live_pinecone) and LangSmith (live_langsmith)
  evals/                    golden, held-out, test and multi-part question sets, baselines.json
  infrastructure/docker/    Dockerfiles for the API and web app, Caddy proxy config, compose file
  infrastructure/terraform/ (planned)
  scripts/                  smoke.sh (post-deploy checks)
  .github/workflows/        ci.yml (seven jobs)
  docs/                     product, architecture, evaluation, operations, implementation
  schemas/                  example manifests and eval cases
```

Not built: a RAGAS and DeepEval runner (on hold), nightly and deploy workflows, and Terraform.

## Dependency rules

- `ingestion` and `answer` never import each other, and neither imports `storage` or `bootstrap`. They talk to the database and indexes only through the interfaces in `domain/ports.py`.
- `domain` imports nothing from the other packages. `storage` imports only `domain`.
- Only `bootstrap.py` (and the CLI that calls it) knows every concrete class.
- The real-service adapters (`adapters/`: local models, OpenAI, Pinecone) are imported only by `bootstrap.py`, so the rest of the code depends on interfaces, not vendors.
- Each question runs in a fresh LangGraph run with no checkpointer, so nothing is shared between questions.
- `evaluation` may import any module but is never imported by the application.
- Retrievers, LLMs, the vector store and the cache sit behind interfaces so providers stay swappable.

`tests/unit/test_architecture_rules.py` enforces the first two rules by inspecting imports.

## Standards

- Python 3.12 with `uv` and a committed lockfile; Ruff, strict mypy and pytest with coverage; TypeScript strict, ESLint and Vitest on the web app.
- Conventional commits, protected `main`, a pull request template, and CODEOWNERS.
- Architecture decision records for every deviation; each source or threshold change is a reviewed commit.
- gitleaks, pip-audit and npm audit gate every pull request.
