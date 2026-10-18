# CiteDesk

CiteDesk is a company-handbook assistant: employees ask questions in plain language and get answers where **every sentence cites the exact handbook passage it came from**. If the handbook does not support an answer, CiteDesk says so instead of guessing.

**Status:** backend core implemented and tested (ingestion, hybrid retrieval, citation verifier, LangGraph answer flow, CLI, retrieval and answer evaluation with quality gates). Runs on offline stand-ins by default or on real local embedding and cross-encoder models. Also a FastAPI layer with signed-in roles and rate limits. Also a Next.js web app: chat with citation chips and a source drawer, and an admin console. Also an OpenAI answer writer with a status bar in the web app, a Pinecone vector index, optional LangSmith tracing and an answer cache. Deliberately not built: an agent loop (measured, not needed: ADR-018) and Graph RAG. Not built yet: RAGAS and DeepEval (on hold), OIDC sign-in, streaming answers, saved conversations and feedback, the quality dashboard.  
**Design baseline:** October 17, 2026  
**Demo corpus:** an openly licensed company handbook, to be chosen after its reuse terms are verified (see [`docs/product/dataset-feasibility.md`](docs/product/dataset-feasibility.md)). Nothing has been downloaded or ingested.

## Why this is a RAG system

The handbook is the organization's own, changing text. A general chatbot does not know a company's current policies, and answers about policy are only useful if the reader can check the clause. CiteDesk adds four things a plain chatbot does not provide:

1. **Checkable citations.** Each sentence links to the passage, page and last-updated date.
2. **Refusal when unsupported.** A verifier blocks uncited or unsupported sentences.
3. **Admin-controlled content.** Admins upload or import documents, preview them, and publish or roll back.
4. **Measured quality.** Faithfulness, answer relevancy and context precision are scored on every pull request and block regressions.

The first release includes a head-to-head against a plain chatbot (see the evaluation strategy). If the plain chatbot matches CiteDesk on the handbook questions, the scope is wrong and we stop and rethink.

## Start here

1. [`docs/product/prd.md`](docs/product/prd.md) — users, features, acceptance criteria, non-goals.
2. [`docs/architecture/technical-architecture.md`](docs/architecture/technical-architecture.md) — components, retrieval, citation verification, agentic flow, contracts.
3. [`docs/architecture/data-flow.md`](docs/architecture/data-flow.md) — step-by-step flows for ingestion, a question, and a gated code change.
4. [`docs/product/dataset-feasibility.md`](docs/product/dataset-feasibility.md) — candidate corpora, licensing status and open questions.
5. [`docs/evaluation/evaluation-strategy.md`](docs/evaluation/evaluation-strategy.md) — metrics, gates, golden questions, CI pipeline, cost controls.
6. [`docs/architecture/deployment.md`](docs/architecture/deployment.md) — environments and operations.
7. [`docs/architecture/project-structure.md`](docs/architecture/project-structure.md) — repository layout and module dependency rules.
8. [`docs/implementation/roadmap.md`](docs/implementation/roadmap.md) — phases, gates and definition of done.
9. [`docs/architecture/adrs.md`](docs/architecture/adrs.md) — decisions and open questions.
10. [`schemas/eval-case.example.json`](schemas/eval-case.example.json) and [`schemas/dataset-manifest.example.yaml`](schemas/dataset-manifest.example.yaml) — example shapes.

## Run it locally

No API keys, Docker or cloud account are needed: the core runs on offline stand-ins and a local SQLite file.

### 1. Install the prerequisites

- **Git** and **[`uv`](https://docs.astral.sh/uv/getting-started/installation/)** (it installs the right Python, 3.12, for you).
- **`make`** is optional; it only wraps the commands in step 4.

### 2. Get the code

```bash
git clone https://github.com/Tevaalgorithms/cite-desk.git
cd cite-desk
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Check that everything works

```bash
make check        # or: uv run ruff check . && uv run mypy && uv run pytest
```

You should see Ruff pass, mypy report no issues, and all tests pass.

### 5. Use the sample handbook

The repo includes a small, made-up handbook at [`data/sample/acme-handbook.md`](data/sample/acme-handbook.md) (fictional company, released as CC0). Example questions with known answers are in [`evals/sample/questions.json`](evals/sample/questions.json).

### 6. Add it, review it, publish it

```bash
uv run citedesk add data/sample/acme-handbook.md --title "Acme Handbook" --license "CC0 (synthetic sample)"
```

This saves the file as a **draft**, so nobody can search it yet, and prints its id, for example `Added e94cbc1cfce6 (2 chunks, draft)`. Publishing requires a recorded `--license`; without one it is refused.

```bash
uv run citedesk list                      # shows each document with its status
uv run citedesk publish <document-id>     # use the id printed above
```

To add and publish in one command, put `--publish` on the `add` line.

### 7. Ask questions

```bash
uv run citedesk ask "How many vacation days do I get?"
uv run citedesk ask "When do I need to return my laptop?"
uv run citedesk ask "What is the capital of France?"
```

The first two answer in the handbook's own words, with `[1]` markers and the section each came from. The third is not in the handbook, so CiteDesk says it can't answer. Try the other questions in `evals/sample/questions.json` too.

### 8. Take a document down

```bash
uv run citedesk unpublish <document-id>
uv run citedesk ask "How many vacation days do I get?"   # now refused
```

### 9. Try your own document

```bash
uv run citedesk add path/to/your-file.md --title "My document" --license "<its license>" --publish
```

Markdown (`.md`), HTML (`.html`) and plain text files are supported. PDF, DOCX and web-page import from the command line are not available yet. The importer exists in code and is tested, but has no command.

### Where things are stored

- Documents, chunks and the audit log are in a SQLite file, `citedesk.local.db`, created in the folder you run the command from. It is git-ignored.
- To start fresh, delete that file. To use another location: `export CITEDESK_DATABASE_URL="sqlite:////full/path/to/file.db"`.
- The vector index is rebuilt in memory every time a command starts.

### Run the web app

Needs Node 22 or newer. With the API from the previous step running on port 8000:

```bash
cd apps/web
npm install
npm run dev                      # http://localhost:3000
```

Sign in by pasting a token from `uv run citedesk token --user you --role analyst` (use `--role admin` for the Admin page). As an admin, add `data/sample/acme-facilities-guide.md` (or the handbook), preview it, and publish it. If you added it without a license, use **Add license** in its table row first; then ask questions as an analyst and click a numbered citation to see the source passage. The API address defaults to `http://localhost:8000`; set `NEXT_PUBLIC_API_URL` to change it, and add the web address to `CITEDESK_CORS_ORIGINS` if it is not `http://localhost:3000`.

Checks (from `apps/web`): `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, and `npm run e2e`, which starts its own API and web server and drives a real browser through sign-in, upload, publish, a cited answer, the source drawer and unpublish (needs `npx playwright install chromium` once).

### Let a language model write the answers (optional)

The default writer quotes the best sentence from the sources: free, no key, but it cannot combine facts and sometimes answers a question from a nearby section. To use OpenAI instead, put your key and a model in `.env` (never in a committed file):

```bash
CITEDESK_WRITER=openai
CITEDESK_OPENAI_API_KEY=<your key>
CITEDESK_OPENAI_MODEL=gpt-5.4-nano       # the cheap default; gpt-5.4-mini is slightly more thorough
```

Every sentence is still checked against its source, and the app refuses rather than guesses. The top bar of the web app shows which model is answering ("Live · openai · gpt-5.4-nano") with a **Check connection** button. Measured quality and cost are in [`docs/evaluation/evaluation-strategy.md`](docs/evaluation/evaluation-strategy.md); a question costs a fraction of a cent. To test the real model: `CITEDESK_RUN_LLM_TESTS=1 uv run pytest tests/llm --no-cov` (a few cents).

### Keep vectors in Pinecone (optional)

By default vectors are kept in memory and rebuilt from the database at every start. To keep them in Pinecone instead (needs `CITEDESK_PINECONE_API_KEY` in `.env` and the real models, because the index size must match the embedding model):

```bash
CITEDESK_MODELS=local CITEDESK_VECTOR_INDEX=pinecone uv run --extra models citedesk pinecone init   # once
CITEDESK_MODELS=local CITEDESK_VECTOR_INDEX=pinecone uv run --extra models citedesk pinecone status
```

Put `CITEDESK_VECTOR_INDEX=pinecone` in `.env` to use it for everything. The database stays the source of truth: at start the index is repaired to match it, and `citedesk pinecone sync` does the same on demand. Each environment uses its own namespace (`CITEDESK_ENVIRONMENT`, default `dev`), so development and production never see each other's vectors. Test against the real index with `CITEDESK_RUN_PINECONE_TESTS=1 uv run --extra models pytest tests/pinecone --no-cov`.

### Trace answers in LangSmith (optional)

Set `CITEDESK_LANGSMITH_TRACING=true` (and `CITEDESK_LANGSMITH_API_KEY`) to record each answer's steps, timings and model call in your LangSmith project. **A trace contains the question and, unless you also set `CITEDESK_LANGSMITH_HIDE_CONTENT=true`, the handbook passages, which leaves this system.** It is off by default. Repeated questions are answered from a small in-memory cache (`CITEDESK_ANSWER_CACHE_SIZE`, `0` turns it off) that is invalidated whenever documents are published or removed.

### Use the real local models (optional)

The default `offline` backend uses word-matching stand-ins. To use a real embedding model and cross-encoder that run on your machine (no API key; model files are downloaded on first use, size not measured):

```bash
uv sync --extra models
export CITEDESK_MODELS=local
uv run citedesk add data/sample/acme-handbook.md --title "Acme" --license "CC0 (synthetic sample)" --publish
uv run citedesk ask "How much time off do I get when I have a baby?"   # a paraphrase the stand-ins refuse
```

### Use Postgres instead of SQLite (optional)

```bash
uv sync --extra postgres
docker run -d --rm --name citedesk-pg -e POSTGRES_PASSWORD=<pick a password> -p 55432:5432 postgres:16-alpine
export CITEDESK_DATABASE_URL="postgresql+psycopg://postgres:<the password>@localhost:55432/postgres"
uv run citedesk list            # creates the tables on first use

# run the Postgres tests
CITEDESK_TEST_POSTGRES_URL="$CITEDESK_DATABASE_URL" uv run pytest tests/integration
```

Tables are created automatically on first start; schema migrations are not implemented yet.

### Run everything in Docker

```bash
cp .env.example .env     # then set CITEDESK_JWT_DEV_SECRET (see the comment in the file)
export CITEDESK_LOCAL_DB_PASSWORD=<pick a password>      # for the bundled trial Postgres
# in .env, point the database at it:
# CITEDESK_DATABASE_URL=postgresql+psycopg://postgres:<that password>@postgres:5432/citedesk
docker compose -f infrastructure/docker/compose.yml --env-file .env --profile local-db up -d --build
scripts/smoke.sh http://localhost                         # quick health and security checks
```

This starts the API, the web app and a Caddy proxy on one address (port 80), plus a trial Postgres with the `local-db` profile. For the Lightsail deployment steps see [`docs/operations/lightsail-deploy.md`](docs/operations/lightsail-deploy.md).

### Run the web API

```bash
export CITEDESK_JWT_DEV_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
uv run citedesk serve                      # http://127.0.0.1:8000

# in another terminal, with the same CITEDESK_JWT_DEV_SECRET exported
ADMIN=$(uv run citedesk token --user alice --role admin)
ANALYST=$(uv run citedesk token --user bob --role analyst)
curl -s localhost:8000/health
curl -s -X POST localhost:8000/v1/chat -H "Authorization: Bearer $ANALYST" \
  -H 'content-type: application/json' -d '{"question":"How many vacation days do I get?"}'
```

Chat and source passages need any signed-in role; document management and the audit log need `admin`. Tokens are for local development only: production should verify tokens from an OIDC provider (planned). Set `CITEDESK_ENABLE_API_DOCS=true` to see interactive docs at `/docs`. Endpoints are listed in [`docs/architecture/technical-architecture.md`](docs/architecture/technical-architecture.md).

### Measure quality

```bash
uv run citedesk eval-retrieval --models offline                    # stand-ins
uv run --extra models citedesk eval-retrieval --models local       # real models
uv run --extra models citedesk eval-retrieval --models local --golden evals/sample/heldout.json
uv run --extra models citedesk eval-retrieval --models local --check evals/baselines.json   # quality gate
```

It prints Recall@1/3/5 and MRR for each retrieval stage, the relevance-threshold calibration, and how many answers were correct, refused or wrongly cited. Results and their limits are in [`docs/evaluation/evaluation-strategy.md`](docs/evaluation/evaluation-strategy.md).

### Good to know

- The default offline stand-ins match on shared words only, so a question phrased with different words than the handbook may be refused. Use the real local models (above) for paraphrases.
- Even with real models, a question the handbook cannot answer can be answered from a nearby section (for example asking about cafeteria prices when only travel meals are covered). The cited passage is shown so you can see this; fixing it needs the language-model writer.
- There is no web chat, API or admin screen yet. See the roadmap.

### Troubleshooting

| Problem | Fix |
| --- | --- |
| `uv: command not found` | Install uv (step 1), then open a new terminal |
| `Record the document's license before publishing` | Re-add the file with `--license "..."` |
| `Same content already added as document ...` | That file is already stored; use `list` to find its id |
| `Only N characters of text found` | The file has too little text (error pages and empty files are rejected on purpose) |
| An answer says it cannot answer | Check the document is published (`list`) and use words close to the handbook's. For example "parental leave" works where "time off for a baby" does not |

## What CiteDesk will do

- **Chat:** streaming answers with citation chips; clicking a chip opens the source drawer at the exact passage.
- **Hybrid retrieval:** in-process BM25 and Pinecone vector search, fused with Reciprocal Rank Fusion, then a cross-encoder reranker.
- **Citation enforcement:** a deterministic verifier checks every sentence; one stricter retry, then an honest refusal.
- **Admin console:** upload files or import URLs, preview chunks, publish, unpublish and roll back, with an audit log.
- **Quality gates:** RAGAS and DeepEval run in GitHub Actions and fail the build below thresholds.
- **Agentic RAG (optional, bounded):** only for multi-part questions, with a hard step budget. It stays only if the evaluation shows it helps.
- **Not included:** Graph RAG (a handbook is mostly prose; see ADR-005).

## Architecture

Solid boxes are built and tested. Dashed boxes are planned (see [`docs/implementation/roadmap.md`](docs/implementation/roadmap.md)).

```mermaid
graph TB
    EMP(["Employee"])
    ADM(["Admin"])
    CLI["CLI - built<br/>citedesk add · publish · ask"]
    WEB["Next.js chat and admin console - planned"]:::planned
    API["FastAPI - planned<br/>auth / RBAC · rate limits · streaming"]:::planned

    subgraph ING["Ingestion package - built"]
        ADD["Add content<br/>file · URL import"] --> FETCH["Parse and check<br/>safe fetch · text checks · duplicate check"] --> CHUNK["Chunk by section<br/>keeps the section path"] --> PUB["Preview, then publish<br/>license required · draft until approved"] --> IDX["Index vectors<br/>bump corpus version · audit log"]
    end

    subgraph ANS["Answer package - built"]
        LOAD["Load published corpus<br/>rebuild BM25 when the version changes"]
        BM["BM25 keyword search"]
        VEC["Vector search"]
        RRF["RRF fusion"]
        RR["Rerank, keep best 6<br/>drop below relevance 0.5"]
        subgraph FLOW["LangGraph flow, a new run for every question"]
            GEN["Write answer<br/>[n] citation markers"]
            VER["Citation verifier<br/>every sentence supported?"]
            GEN --> VER
            VER -- "fail: retry once" --> GEN
        end
        ROUTE["Router and agent loop - planned<br/>multi-step questions"]:::planned
        LOAD --> BM & VEC
        BM --> RRF
        VEC --> RRF
        RRF --> RR --> GEN
    end

    SQL[("SQL database<br/>documents · chunks · audit log · corpus version<br/>SQLite and Postgres tested")]
    VIDX[("Vector index<br/>in-memory stand-in · Pinecone planned")]
    OUT(["Answer with citations<br/>or honest refusal"])
    LS[("LangSmith traces - planned")]:::planned

    EMP --> CLI --> LOAD
    ADM --> CLI --> ADD
    EMP -.-> WEB -.-> API -.-> LOAD
    VER -- pass --> OUT
    VER -- "fail twice" --> OUT
    RR -- "nothing relevant" --> OUT
    IDX --> SQL
    IDX --> VIDX
    LOAD --- SQL
    VEC --- VIDX
    ANS -.-> LS
    classDef planned stroke-dasharray: 5 5,stroke:#888
```

Ingestion and the answer package never call each other. They meet only through the SQL database, the vector index and the shared interfaces in `src/citedesk/domain/ports.py`.

### Quality gate in CI

```mermaid
graph LR
    PR["Pull request"] --> S1["Lint · types · tests · secret scan<br/>built: .github/workflows/ci.yml"]
    S1 --> S2["Dependency audit<br/>planned"]:::planned
    S2 --> S3["Retrieval metrics and RAGAS + DeepEval<br/>planned"]:::planned
    S3 --> G{"All gates<br/>pass?"}
    G -- yes --> M["Merge allowed"]
    G -- no --> F["Build fails<br/>metrics table on the PR"]
    M --> N["Nightly: full set + ablation ladder<br/>planned"]:::planned
    classDef planned stroke-dasharray: 5 5,stroke:#888
```

Today CI runs Ruff, strict mypy and pytest, the web checks, a browser end-to-end test, the Postgres tests, the real-model quality gates, an image build and a gitleaks secret scan. The RAGAS and DeepEval gates are designed in [`docs/evaluation/evaluation-strategy.md`](docs/evaluation/evaluation-strategy.md) but not implemented.

## Sequence diagrams

These follow the code in `src/citedesk/`. Steps marked planned do not exist yet.

### Ingestion path (admin adds a document)

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Ing as IngestionService
    participant Fetch as UrlFetcher
    participant Repo as SQL repository
    participant Emb as Embedder
    participant Idx as Vector index

    Note over Admin,Ing: Today the CLI calls IngestionService directly. The admin console and API are planned.
    Admin->>Ing: add_text (file) or add_url (web page)
    opt URL import
        Ing->>Fetch: fetch(url)
        Note over Fetch: http/https only, public IPs only, every redirect rechecked, size limit, robots.txt honoured
        Fetch-->>Ing: page text, or UnsafeUrlError / FetchError
    end
    Ing->>Ing: parse into sections (rejects pages with too little text)
    Ing->>Repo: find_by_hash (duplicate check)
    Ing->>Ing: chunk each section
    Ing->>Repo: add_document as draft with its chunks (audit: add)
    Ing-->>Admin: document id
    Admin->>Ing: preview(id)
    Ing-->>Admin: chunks with section paths
    Admin->>Ing: publish(id)
    Ing->>Ing: check that a license is recorded
    Ing->>Emb: embed chunk texts
    Ing->>Idx: upsert vectors
    Ing->>Repo: transition to published (status, corpus version +1, audit) in one transaction
    Note over Ing,Idx: If the upsert or the transition fails, the vectors are deleted and the document stays a draft
    Ing-->>Admin: published
    Note over Repo: The BM25 keyword index is not built here. The answer package rebuilds it when it sees the new corpus version.
    opt take a document down
        Admin->>Ing: unpublish(id)
        Ing->>Idx: delete the document's vectors
        Ing->>Repo: transition to retired (corpus version +1, audit)
    end
```

### Retrieval and answer path (employee asks a question)

```mermaid
sequenceDiagram
    autonumber
    actor Emp as Employee
    participant Ans as AnswerService
    participant Repo as SQL repository
    participant Flow as LangGraph flow
    participant Ret as HybridRetriever
    participant BM as BM25 index
    participant Idx as Vector index
    participant RR as Reranker
    participant W as Answer writer
    participant Ver as Citation verifier

    Note over Emp,Ans: Today the CLI calls AnswerService directly. Auth, rate limits, the answer cache, saved conversations and LangSmith tracing are planned.
    Emp->>Ans: ask(question)
    Ans->>Repo: corpus_version()
    opt the version changed since the last question
        Ans->>Repo: published_passages()
        Ans->>BM: rebuild the keyword index
    end
    Ans->>Flow: start a new flow for this question (no shared state)
    Flow->>Ret: retrieve(question)
    Ret->>BM: keyword search (top 20)
    Ret->>Idx: embed the question, vector search (top 20)
    Ret->>Ret: fuse with Reciprocal Rank Fusion (best 30)
    Ret->>RR: rerank
    RR-->>Ret: passages with relevance scores
    Ret-->>Flow: best 6 passages
    Note over Flow,Ans: Passages below the relevance threshold (0.5) are dropped
    alt no passages left
        Flow-->>Emp: refusal (nothing_relevant_found)
    else passages found
        loop up to 2 attempts, stops when verified
            Flow->>W: write(question, passages, strict on the retry)
            W-->>Flow: draft with [n] markers
            Flow->>Ver: verify every sentence
            Ver-->>Flow: pass, or the list of problems
        end
        alt verified
            Flow-->>Emp: answer with citations
        else still unverified after 2 attempts
            Flow-->>Emp: refusal (could_not_verify_answer)
        end
    end
    Emp->>Ans: source_passage(chunk id)
    Ans->>Repo: get_passage (published content only)
    Repo-->>Emp: the passage, section and document for the source drawer
```

## Technology stack

| Layer | Choice |
| --- | --- |
| API | Python 3.12, FastAPI, Pydantic, `uv` |
| Orchestration | LangGraph (answer flow, optional agent), LangChain (model and retriever integrations) |
| Keyword search | In-process BM25 |
| Vector search | Pinecone dense index |
| Reranker | Cross-encoder (local ONNX model by default) |
| LLM | OpenAI behind an interface so another provider can be added |
| Metadata store | PostgreSQL |
| Observability | LangSmith, OpenTelemetry, structured logs |
| Evaluation | RAGAS, DeepEval, pytest, GitHub Actions |
| Frontend | Next.js, React, TypeScript, plain CSS |
| Quality tooling | Ruff, strict mypy, pytest, Vitest, Playwright, gitleaks, pip-audit, npm audit |

## Repository structure

```text
cite-desk/
  apps/web/                 Next.js: chat, admin console (quality dashboard planned)
  src/citedesk/
    domain/                 shared data models and interfaces (ports)      [built]
    ingestion/              parse, chunk, safe URL fetch, publish workflow [built]
    answer/                 BM25, fusion, retrieval, writer, verifier, LangGraph flow [built]
    storage/                SQL repository, offline dev adapters           [built]
    bootstrap.py, cli.py    wiring and command line                        [built]
    api/                    FastAPI routes, dev sign-in tokens and roles, rate limits  [built]
    llm/                    OpenAI, Pinecone and cross-encoder adapters    [planned]
    evaluation/             RAGAS and DeepEval runners, thresholds         [planned]
  evals/                    golden sets, thresholds, baselines
  infrastructure/docker/    Dockerfiles, Caddy proxy config and compose file  [built]
  infrastructure/terraform/ (planned)
  scripts/                  smoke.sh: post-deploy checks
  .github/workflows/        CI, PR evaluation, nightly evaluation, deploy
  docs/                     product, architecture, evaluation, implementation
  schemas/                  example manifests and eval cases
```

See [`docs/architecture/project-structure.md`](docs/architecture/project-structure.md) for the dependency rules between modules.

## Limits and honest caveats

- **Specification only.** Thresholds in the evaluation strategy are starting guesses; they are calibrated on the first measured baseline.
- **"Production-ready" means** the tests, gates, monitoring, backups and runbook exist and have been exercised. It does not mean the system has run under real load or on confidential data.
- **LLM judges vary** between runs, so gates use tolerance bands and cached judgments.
- **Corpus licensing is unverified.** No document is ingested until its terms are recorded in the source registry.
- CiteDesk gives information from the handbook it is given. It is not HR, legal or compliance advice.

## License

GPL-3.0. See [`LICENSE`](LICENSE).
