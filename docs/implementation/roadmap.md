# CiteDesk — Roadmap

Phases run in order and each ends at a gate that must pass before the next starts. Phases are not dated; dates are set once the open decisions in the ADRs are answered. Implement one ticket at a time.

| Phase | Scope | Gate |
| --- | --- | --- |
| 0 — Foundations and head-to-head | Repo tooling, CI skeleton, secret scan, Compose with Postgres, `/health`; write the 30-question head-to-head and run it against plain chatbots | CI green; head-to-head result written down; scope kept or revised |
| 1 — Data | Verify corpus terms; source registry; fetch, parse, chunk with provenance; quality checks | Corpus size measured; license and terms recorded for every source |
| 2 — Retrieval | BM25, Pinecone store, RRF, cross-encoder; golden retrieval set | Recall@5 meets the calibrated gate; ablation of BM25, vectors, hybrid, rerank recorded |
| 3 — Answers and citations | LangGraph answer flow, answer generation, citation verifier, refusal paths | 100% citation tests pass; unanswerable questions refused at or above the gate |
| 4 — Product | Streaming chat, source drawer, admin console (upload, import, preview, publish, rollback), audit log | Playwright flows pass for chat and admin |
| 5 — Evaluation in CI | RAGAS and DeepEval jobs, thresholds, PR comment, nightly run, LangSmith experiments | Gates enforced on `main`; baseline stored |
| 6 — Agent trial | Bounded agent for multi-part questions; compare against hybrid on the multi-step set | Kept only if a metric improves; otherwise disabled and documented |
| 7 — Hardening | Security review, license review, runbook, backup and restore test, load test, measure memory and latency and size the Lightsail instance | Reviews signed off; restore tested |

## Status

Implemented offline on the stand-ins (ADR-012): the domain models and interfaces, SQL repository, parsing, chunking, safe URL fetching, the publish and unpublish workflow with license gate and audit log, BM25, fusion, hybrid retrieval, the citation verifier, the LangGraph answer flow with retry and refusal, and a CLI. Covers parts of Phases 1 to 3. Since then: real local embedding and cross-encoder adapters, the retrieval and answer evaluation harness with golden, held-out and test sets, threshold calibration, and baseline gates (the retrieval part of the Phase 2 gate, on a small synthetic sample). Also built: the Next.js chat and admin console with a real-browser end-to-end test (17 checks), and the FastAPI layer (dev sign-in tokens, roles, rate limits, admin endpoints, source passages). The OpenAI answer writer is built and measured (ADR-017). Still to do: the Pinecone index, OIDC sign-in, streaming answers, quality dashboard, RAGAS and DeepEval in CI, the larger reviewed golden set, migrations.

## Definition of done (per ticket)

- Tests written and passing: unit tests offline with mocked providers, integration tests against local services.
- Ruff, strict mypy and the relevant tests pass; failures are reported with their output.
- Documentation updated in the same change; deviations recorded as ADRs.
- A secret scan of the staged diff is clean.

## Starter tickets (Phase 0)

- P0-001 Project tooling: `uv`, Ruff, mypy strict, pytest, Makefile.
- P0-002 Docker Compose with Postgres and `.env.example`.
- P0-003 CI: lint, types, tests, gitleaks, dependency audit.
- P0-004 FastAPI app with `/health`, `/ready` and request-id logging.
- P0-005 Head-to-head question set and results template.
