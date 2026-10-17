# CiteDesk — Architecture Decision Records

Status key: **Accepted** (decided), **Proposed** (recommended, needs confirmation), **Open** (undecided).

## ADR-001 — Use RAG over the handbook, with a stated falsifier
**Accepted.** The handbook is an organization's own, changing text, and users need checkable citations. The decision is falsifiable: the head-to-head against a plain chatbot must show an advantage on handbook-specific questions, or the scope is revisited.

## ADR-002 — Hybrid retrieval with in-process BM25 and Pinecone
**Accepted.** BM25 handles exact policy and form names; vectors handle plain-language phrasing. Results are fused with Reciprocal Rank Fusion (k=60). Consequence: each worker must load the same corpus version; revisit at about a million chunks.

## ADR-003 — Cross-encoder reranking
**Accepted.** Rerank the top 30 fused candidates and keep the best 6 (configurable). Local model by default; adds a few hundred milliseconds.

## ADR-004 — Model provider and data handling
**Open.** OpenAI behind an interface is the working assumption. Before any real or confidential documents are loaded, decide hosted versus self-hosted models and retention settings. Until then only public or synthetic documents are used.

## ADR-005 — No Graph RAG; bounded agent only if it earns its place
**Accepted.** A handbook is mostly prose with page and section links, so a graph adds little. The optional agent (max 4 steps, 6 retrievals, 15 seconds) is kept only if the multi-step evaluation shows a gain. Revisit Graph RAG only if questions appear that cannot be answered otherwise.

## ADR-006 — No per-document access control in the MVP
**Proposed.** The MVP assumes one handbook readable by all signed-in employees. Per-document access groups, tenant isolation and leak tests are a later extension; if added, filters must apply inside retrieval before ranking.

## ADR-007 — Citation enforcement by deterministic verifier
**Accepted.** Every sentence needs a valid marker; quotes, numbers, dates and names must appear in the cited passage. One stricter retry, then refusal. Status lines come from code.

## ADR-008 — Evaluation gates are calibrated, not guessed
**Accepted.** Starting thresholds are guesses and are calibrated on the first baseline, then ratcheted up. They are never loosened to pass a failing run. Judged evaluation uses a pinned judge, temperature 0, cached judgments and call caps.

## ADR-009 — Modular monolith, Docker Compose first
**Accepted.** One FastAPI service with background workers; a single host for the MVP. Managed containers and databases come only when uptime or traffic requires them.

## ADR-010 — Exact-key answer cache only
**Accepted.** Cache key includes the normalized question, corpus version and prompt and model versions. No semantic answer caching in the MVP.

## ADR-011 — Corpus licensing gate
**Accepted.** No document is ingested until its license and terms URL are recorded and an admin marks it publishable. Restricted sources cannot be published.

## ADR-012 — Offline stand-ins until the real adapters exist
**Accepted.** The first implementation uses a hashing embedder, an in-memory vector index, a word-overlap reranker and an extractive answer writer so everything runs and tests offline. They are labelled as stand-ins in code. Retrieval and answer quality must not be judged until the Pinecone index, a real embedding model, a cross-encoder and an LLM writer replace them. The relevance threshold (`min_relevance`) is tuned to the overlap reranker and must be recalibrated with the cross-encoder. The default (0.5: a passage must cover at least half of the question's content words) is deliberately strict: with the stand-ins, rephrased questions are refused rather than answered from a loosely matching passage. This means the sample handbook only answers questions that reuse its wording.

## ADR-013 — One SQL repository for SQLite and Postgres
**Accepted.** SQLAlchemy serves SQLite for local work and tests, and Postgres (a free-tier managed instance is the intended first deployment) through the connection URL. Table creation at startup stands in for migrations, which are a later ticket. Pinecone remains a rebuildable copy, not the system of record.

## ADR-014 — Verification checks faithfulness, not relevance
**Accepted.** The citation verifier proves every sentence is supported by the passage it cites. It cannot tell whether the cited passage answers the question, so relevance is enforced separately (reranker score threshold, and the writer using only passages close to the best match). A test caught an unrelated passage passing verification; it is now a regression test.

## Open questions

1. Which corpus (see dataset feasibility) and under what attribution?
2. Who reviews the golden questions?
3. OpenAI only, or also Claude behind the same interface?
4. Hosting target and evaluation budget cap.
