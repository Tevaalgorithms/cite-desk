# CiteDesk

CiteDesk is a company-handbook assistant: employees ask questions in plain language and get answers where **every sentence cites the exact handbook passage it came from**. If the handbook does not support an answer, CiteDesk says so instead of guessing.

**Status:** specification and scaffold only; no application code yet.  
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

## What CiteDesk will do

- **Chat:** streaming answers with citation chips; clicking a chip opens the source drawer at the exact passage.
- **Hybrid retrieval:** in-process BM25 and Pinecone vector search, fused with Reciprocal Rank Fusion, then a cross-encoder reranker.
- **Citation enforcement:** a deterministic verifier checks every sentence; one stricter retry, then an honest refusal.
- **Admin console:** upload files or import URLs, preview chunks, publish, unpublish and roll back, with an audit log.
- **Quality gates:** RAGAS and DeepEval run in GitHub Actions and fail the build below thresholds.
- **Agentic RAG (optional, bounded):** only for multi-part questions, with a hard step budget. It stays only if the evaluation shows it helps.
- **Not included:** Graph RAG (a handbook is mostly prose; see ADR-005).

## Architecture

```mermaid
graph TB
    EMP(["Employee<br/>Next.js chat"])
    ADM(["Admin<br/>Next.js console"])
    API["FastAPI backend<br/>auth / RBAC · rate limits · streaming"]

    subgraph ING["Ingestion path"]
        ADD["Add content<br/>upload · URL import"] --> FETCH["Fetch and parse<br/>network guards · text checks · dedupe"] --> CHUNK["Chunk with provenance<br/>page · section · license · date"] --> PUB["Preview and publish<br/>draft until approved"] --> IDX["Index and version<br/>chunks · vectors · keyword index"]
    end

    subgraph LG["LangGraph answer flow"]
        ROUTE["Router<br/>simple · multi-step · refuse"]
        BM["BM25<br/>in-process"]
        VEC["Vector search<br/>Pinecone"]
        RRF["RRF fusion"]
        RR["Cross-encoder rerank<br/>top 30 to 6-8"]
        GEN["Answer generation<br/>[n] citation markers"]
        VER["Citation verifier<br/>every sentence supported?"]
        AGT["Agent loop (optional)<br/>max 4 steps · 6 retrievals · 15 s"]
        ROUTE --> BM & VEC
        BM --> RRF
        VEC --> RRF
        RRF --> RR --> GEN --> VER
        ROUTE -. multi-step .-> AGT -.-> BM
    end

    PG[("Postgres<br/>documents · chunks · versions<br/>conversations · audit log")]
    PC[("Pinecone<br/>dense vectors")]
    OUT(["Answer with citations<br/>or honest refusal"])
    LS[("LangSmith<br/>traces · experiments")]

    EMP --> API --> ROUTE
    VER -- pass --> OUT
    VER -- "fail: retry once, then refuse" --> OUT
    ADM --> API --> ADD
    IDX --> PG
    IDX --> PC
    BM --- PG
    VEC --- PC
    LG -.-> LS
```

### Quality gate in CI

```mermaid
graph LR
    PR["Pull request"] --> S1["Lint · types · unit tests<br/>secret scan · dependency audit"]
    S1 --> S2["Retrieval and citation checks<br/>fixed corpus snapshot"]
    S2 --> S3["RAGAS + DeepEval<br/>36-question subset<br/>pinned judge · cached"]
    S3 --> G{"All gates<br/>pass?"}
    G -- yes --> M["Merge allowed"]
    G -- no --> F["Build fails<br/>metrics table on the PR"]
    M --> N["Nightly: full set + ablation ladder<br/>results to LangSmith"]
```

## Sequence diagrams

### Ingestion path (admin adds a document)

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Web as Next.js console
    participant API as FastAPI
    participant Fetch as Fetcher and parser
    participant PG as Postgres
    participant Emb as Embedding model
    participant PC as Pinecone
    participant BM as BM25 index

    Admin->>Web: Upload file or paste URL
    Web->>API: POST /v1/admin/documents or /imports
    API->>API: Check role (admin) and file type and size
    API->>Fetch: Fetch and parse
    Note over Fetch: http/https only, private addresses blocked,<br/>size and redirect limits, robots.txt honoured
    Fetch-->>API: Clean text, or rejection (error page, duplicate hash)
    API->>PG: Save document as draft with source, license, content hash
    API->>Fetch: Chunk by section with page and offsets
    Fetch-->>API: Chunks with provenance
    API->>PG: Save chunks (status draft)
    API-->>Web: Preview of chunks
    Admin->>Web: Review, exclude chunks, approve
    Web->>API: POST /v1/admin/documents/{id}/publish
    API->>Emb: Embed chunks
    Emb-->>API: Vectors
    API->>PC: Upsert vectors with published metadata
    API->>BM: Rebuild keyword index from published chunks
    API->>PG: Mark published, bump corpus version, write audit log
    API-->>Web: Published (new corpus version; cached answers invalidated)
    Note over API,PG: If any index step fails, the previous version stays live
```

### Retrieval and answer path (employee asks a question)

```mermaid
sequenceDiagram
    autonumber
    actor Emp as Employee
    participant Web as Next.js chat
    participant API as FastAPI
    participant Graph as LangGraph router
    participant BM as BM25 index
    participant PC as Pinecone
    participant RR as Cross-encoder
    participant LLM as Answer model
    participant Ver as Citation verifier
    participant PG as Postgres
    participant LS as LangSmith

    Emp->>Web: Ask a question
    Web->>API: POST /v1/chat
    API->>API: Authenticate, rate limit
    API->>PG: Exact-key cache lookup (question, corpus and prompt versions)
    alt cache hit
        PG-->>API: Stored verified answer
        API-->>Web: Stream cached answer with citations
    else cache miss
        API->>Graph: Start run with a new per-request thread id
        Graph->>Graph: Classify: simple, multi-step or refuse
        par keyword search
            Graph->>BM: Query published chunks
            BM-->>Graph: Ranked chunks
        and vector search
            Graph->>PC: Embed query and search published chunks
            PC-->>Graph: Ranked chunks
        end
        Graph->>Graph: Fuse with Reciprocal Rank Fusion
        Graph->>RR: Rerank top 30
        RR-->>Graph: Best 6 to 8 passages
        opt multi-step question
            Graph->>Graph: Agent loop (max 4 steps, 6 retrievals, 15 s)
        end
        Graph->>LLM: Numbered passages and question
        LLM-->>Graph: Draft answer with [n] markers
        Graph->>Ver: Check every sentence
        alt verified
            Ver-->>Graph: Pass
        else failed
            Graph->>LLM: Retry once, quotes only
            LLM-->>Graph: Second draft
            Graph->>Ver: Check again
            Ver-->>Graph: Pass or fail
        end
        Graph-->>API: Verified answer, or refusal
        API->>PG: Store message record and cache verified answer
        API-->>Web: Stream answer with citation chips
        API-->>LS: Trace of every step
    end
    Emp->>Web: Click a citation chip
    Web->>API: GET /v1/chunks/{id}
    API->>PG: Fetch published passage, page, section, last updated
    API-->>Web: Source drawer at the exact passage
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
| Frontend | Next.js, TypeScript, Tailwind, shadcn/ui |
| Quality tooling | Ruff, strict mypy, pytest, Vitest, Playwright, gitleaks, pip-audit, npm audit |

## Repository structure

```text
cite-desk/
  apps/web/                 Next.js: chat, admin console, quality dashboard
  src/citedesk/
    api/                    FastAPI routes, auth, rate limits, streaming
    ingestion/              sources, fetchers, parsers, chunking, provenance
    retrieval/              BM25, Pinecone store, fusion, reranker
    agents/                 LangGraph answer flow, router, step budget
    citations/              verifier and answer formatter
    llm/                    model and embedding adapters
    evaluation/             RAGAS and DeepEval runners, thresholds, reports
    db/                     schema and migrations
  evals/                    golden sets, thresholds, baselines
  infrastructure/           docker, terraform
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
