# CiteDesk — Technical Architecture

A modular FastAPI monolith with background workers: simpler to run and test than separate services, and enough for the MVP. See the diagram in the README and the step-by-step flows in [`data-flow.md`](data-flow.md).

## Components

| Component | Responsibility |
| --- | --- |
| `api` | Routes, auth (OIDC/JWT), rate limits, server-sent-event streaming |
| `ingestion` | Source registry, safe fetchers, parsers, chunking, provenance, quality checks |
| `retrieval` | BM25 index, Pinecone store, Reciprocal Rank Fusion, cross-encoder reranker |
| `agents` | LangGraph answer flow, router, optional agent loop, step budget |
| `citations` | Verifier and answer formatter |
| `llm` | Model and embedding adapters behind interfaces |
| `evaluation` | RAGAS and DeepEval runners, thresholds, reports |
| `db` | Schema and migrations |

## Retrieval

| Stage | Choice | Reason |
| --- | --- | --- |
| Chunking | Section-aware; one chunk per heading section with a size cap and a one-sentence overlap between consecutive chunks of a long section; each chunk keeps source, section path, page and character offsets | Questions target sections; citations need exact locations |
| Keyword search | In-process BM25 over the chunk store, rebuilt on publish | Exact policy names, form names, numbers |
| Vector search | Pinecone dense index with a metadata filter for published status | Meaning ("quit" matches "resignation") |
| Fusion | Reciprocal Rank Fusion, k=60 | No score calibration across two scorers |
| Rerank | Cross-encoder on the top 30 fused candidates; keep 6 to 8 | Largest single quality gain; adds a few hundred milliseconds |
| Filters | Only published, current versions by default | Drafts never reach users |

Limits: in-process BM25 suits roughly up to a million chunks and is rebuilt per instance; each worker must load the same corpus version. Past that scale, move keyword search behind the same interface to Pinecone sparse vectors or OpenSearch. The Pinecone free-tier limits must be checked at build time.

Embeddings: a local 384-dimension model by default, or an OpenAI embedding shortened to the same size. The model id is stored with every vector so a change forces a visible re-embed.

## Citation enforcement

1. The model receives numbered passages and must end each sentence with markers such as `[2]`.
2. A deterministic verifier checks each sentence: it has a marker, the marker exists, quoted text appears verbatim in the cited passage, and numbers, dates and names appear in the cited text.
3. Paraphrased sentences get a support check against their cited passage.
4. Failure triggers one stricter regeneration (quotes only); a second failure becomes a refusal.
5. Status lines such as "last updated" and "document version" come from code, never from the model.

Stored with every answer: question hash, retrieved chunk ids and scores, verification result, model and prompt versions, corpus version.

## Agentic flow (optional)

A LangGraph flow: route, decompose, retrieve, grade evidence, generate, verify. Hard limits: 4 steps, 6 retrieval calls, 15 seconds. It uses the same retrievers and the same verifier. It handles multi-part questions, one query rewrite when evidence is weak, and one clarifying question when a question is ambiguous. It stays in the product only if the multi-step evaluation set shows a measurable gain over plain hybrid retrieval (starting rule: at least 2 points on faithfulness or context precision).

Lesson carried over from an earlier project: never reuse a LangGraph checkpoint thread across requests; use a per-request id.

## Data model

| Table | Key fields |
| --- | --- |
| `source` | id, name, publisher, license, terms_url, refresh_schedule, restricted |
| `document` | id, source_id, title, url, content_hash, version, status (draft, published, retired), retrieved_at, published_at |
| `chunk` | id, document_id, section_path, page_start, page_end, char_start, char_end, text, embedding_model, pinecone_id |
| `conversation`, `message` | id, session id, question hash, answer, verification result, retrieved chunk ids, model and prompt versions, corpus version |
| `review_label` | message_id, reviewer, verdict, note |
| `audit_log` | actor, action, target, time, outcome |

## API surface

| Endpoint | Purpose | Access |
| --- | --- | --- |
| `POST /v1/chat` | Ask a question; stream the answer with citations | Employee |
| `GET /v1/chunks/{id}` | Passage for the source drawer | Employee (published only) |
| `POST /v1/feedback` | Thumbs up or down with a note | Employee |
| `POST /v1/admin/documents`, `/imports` | Upload a file or import a URL | Admin |
| `GET /v1/admin/documents/{id}/preview` | Parsed chunks before publishing | Admin |
| `POST /v1/admin/documents/{id}/publish` (and unpublish, rollback) | Publish control | Admin |
| `GET /v1/admin/audit` | Audit log | Admin |
| `POST /v1/admin/reviews` | Label an answer | Reviewer |
| `GET /v1/quality/runs` | Evaluation results | Admin, reviewer |
| `GET /health`, `/ready` | Probes | Open |

## Security

- Admin and reviewer actions require OIDC sign-in with roles; chat requires sign-in in the default mode and is rate limited per user and per IP.
- Web import blocks private, loopback and metadata addresses, limits redirects, size and content types, and honours robots.txt.
- Uploaded files are validated by type and size, stored privately and parsed in a sandboxed worker.
- Retrieved text is untrusted: tools are chosen by code, never by document text. Prompt-injection documents are part of the evaluation set.
- Secrets live in a secrets manager; gitleaks and dependency audits run on every pull request.

## Observability

LangSmith traces one run per question (router, retrievers, fusion, reranker, generation, verification). Structured logs carry a request id. Dashboards track p95 latency per stage, refusal rate, verification-failure rate, cache hit rate and cost per question.

Latency targets (p95): BM25 under 50 ms, Pinecone query under 300 ms, rerank of 30 candidates under 400 ms, first streamed token under 2.5 s, complete simple answer under 8 s, agentic answer under 15 s (hard limit). These are targets to be measured, not results.
