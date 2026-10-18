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
**Accepted.** SQLAlchemy serves SQLite for local work and tests, and Postgres (a free-tier managed instance is the intended first deployment) through the connection URL. The workflow is tested on both: `tests/integration` runs it against Postgres 16 (a CI job and a local Docker container). That run caught a bug SQLite had hidden (chunks inserted before their document); SQLite now enforces foreign keys too. Table creation at startup stands in for migrations, which are a later ticket. Pinecone remains a rebuildable copy, not the system of record.

## ADR-014 — Verification checks faithfulness, not relevance
**Accepted.** The citation verifier proves every sentence is supported by the passage it cites. It cannot tell whether the cited passage answers the question, so relevance is enforced separately (reranker score threshold, and the writer using only passages close to the best match). A test caught an unrelated passage passing verification; it is now a regression test.

## ADR-015 — MVP hosting on a single Lightsail instance
**Accepted.** The MVP runs on one Amazon Lightsail instance with Docker Compose, chosen for low, flat cost and minimal operations (starting plan $12 per month for 2 GB RAM, from AWS's pricing page read on 2026-10-17). Consequences: a single point of failure and downtime during deploys, accepted for the MVP. Secrets use a root-only environment file written by the deploy job, because Lightsail instance identity for SSM is unconfirmed. The database is an external free-tier Postgres, a Lightsail managed database ($15 per month and engine to be confirmed), or SQLite for a first single-instance deployment; the choice is still open. Move to ECS when more than one instance, zero-downtime deploys or role-based secrets are needed. Supersedes the "Hosting target" open question.

## ADR-016 — Local models, raw reranker scores, and held-out evaluation
**Accepted.** A `local` backend runs a real embedding model (BAAI/bge-small-en-v1.5) and cross-encoder (ms-marco MiniLM) on the developer's machine through fastembed, with no API key (`uv sync --extra models`). The `offline` stand-ins stay as the default so tests and CI need no downloads. The cross-encoder's score is kept raw (a logit, typically between about -12 and +8), so the relevance threshold is set per backend and is calibrated with `citedesk eval-retrieval`, never copied between backends. Calibrated on the sample handbook at -10.0 for `local`: it refuses every known unanswerable question at the cost of the two hardest paraphrases. Evaluation uses three question sets so the headline number is honest: `golden` (used to calibrate), `heldout` (used for diagnosis, so now a validation set) and `test` (run once, not gated, to avoid tuning on it). Known limit: a relevance score measures topical closeness, not whether the answer exists, so an unanswerable question about a topic the handbook covers (for example "How much does the cafeteria lunch cost?") can still be answered from the nearby passage. The language-model writer and RAGAS answer-relevancy checks are the planned defence. The extractive writer quotes only the best passage because adding sentences from lower-ranked passages cited unrelated sections.

## ADR-017 — OpenAI answer writer, cheap model by default, model as a setting
**Accepted.** The answer text is written by an OpenAI model (`CITEDESK_WRITER=openai`) that is told to use only the numbered passages, to cite every sentence, and to reply `NO_ANSWER` when the passages do not answer. Its output is never trusted: the deterministic citation verifier still checks every sentence, and `NO_ANSWER`, an unreachable model and unverifiable drafts each become a distinct honest refusal (`passages_do_not_answer`, `model_unavailable`, `could_not_verify_answer`). The default model is `gpt-5.4-nano`, chosen by measurement (see the evaluation strategy), and the model name is a setting (`CITEDESK_OPENAI_MODEL`, stored in SSM as a plain `String` parameter), so changing it needs no code change. The built-in quoting writer stays the default so the project runs with no key and no cost. The web app shows the active model and a "Check connection" button; the check makes one tiny real request, and the server reuses a recent result (never fresher than 15 seconds, 5 minutes on page load) so neither page loads nor clicks can run up the bill. Consequences: answers now depend on a third-party service (its outages become a clear "model unavailable" message), and question text and passages are sent to OpenAI (see ADR-004).

## Open questions

1. Which corpus (see dataset feasibility) and under what attribution?
2. Who reviews the golden questions?
3. OpenAI only, or also Claude behind the same interface?
4. Which Postgres (free-tier provider, Lightsail managed database, or SQLite first), and the evaluation budget cap.
