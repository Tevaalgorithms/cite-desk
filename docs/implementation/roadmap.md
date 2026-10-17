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
| 7 — Hardening | Security review, license review, runbook, backup and restore test, load test | Reviews signed off; restore tested |

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
