# CiteDesk — Project Structure

```text
cite-desk/
  apps/web/                 Next.js: chat, admin console, quality dashboard
  src/citedesk/
    domain/                 shared data models and interfaces (ports)
    ingestion/              parsing, chunking, safe URL fetching, publish workflow
    answer/                 BM25, fusion, retrieval, rerankers, writers, verifier, LangGraph flow
    storage/                SQL repository and offline dev adapters
    bootstrap.py            the only place that wires ingestion and answer together
    cli.py                  local command line
    api/                    (planned) FastAPI routes, auth, rate limits, streaming
    llm/                    (planned) OpenAI, Pinecone and cross-encoder adapters
    evaluation/             (planned) RAGAS and DeepEval runners, thresholds, reports
  tests/                    unit and integration tests, deterministic fixtures
  evals/                    golden sets, thresholds.yaml, baselines, reports
  infrastructure/           docker, terraform
  .github/workflows/        ci.yml, eval-pr.yml, eval-nightly.yml, deploy.yml
  docs/                     product, architecture, evaluation, implementation
  schemas/                  example manifests and eval cases
```

`domain`, `ingestion`, `answer`, `storage`, `bootstrap` and `cli` are implemented; the rest are added phase by phase per the roadmap.

## Dependency rules

- `ingestion` and `answer` never import each other, and neither imports `storage` or `bootstrap`. They talk to the database and indexes only through the interfaces in `domain/ports.py`.
- `domain` imports nothing from the other packages. `storage` imports only `domain`.
- Only `bootstrap.py` (and the CLI that calls it) knows every concrete class.
- Each question runs in a fresh LangGraph run with no checkpointer, so nothing is shared between questions.
- `evaluation` may import any module but is never imported by the application.
- Retrievers, LLMs, the vector store and the cache sit behind interfaces so providers stay swappable.

`tests/unit/test_architecture_rules.py` enforces the first two rules by inspecting imports.

## Standards

- Python 3.12 with `uv` and a committed lockfile; Ruff, strict mypy and pytest with coverage; TypeScript strict, ESLint and Vitest on the web app.
- Conventional commits, protected `main`, a pull request template, and CODEOWNERS.
- Architecture decision records for every deviation; each source or threshold change is a reviewed commit.
- gitleaks, pip-audit and npm audit gate every pull request.
