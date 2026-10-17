# CiteDesk — Deployment

Three environments, one container image per service, and the same pipeline that runs the evaluation gates also deploys.

| Environment | Purpose | Data and services |
| --- | --- | --- |
| Local | Development | Docker Compose with Postgres; a personal Pinecone free-tier index or an in-memory store; mock model for offline tests; a local OIDC stub |
| CI (GitHub Actions) | Gates on every pull request | Throwaway Pinecone namespace per run, fixed corpus snapshot, cached judge calls |
| Production | Users | One small host running Docker Compose behind a TLS-terminating proxy, Postgres with nightly backups, a real Pinecone index, secrets in a secrets manager |

## Delivery pipeline

1. **Pull request:** lint, types, tests, verifier tests, retrieval and judged gates, secret scan, dependency audit.
2. **Merge to main:** build and scan images, run the full evaluation, deploy only if every gate passes.
3. **Post-deploy:** health check, smoke questions (a lookup, a multi-part question, a refusal), automatic rollback on failure.

## Operations

- Infrastructure as code (Terraform) for the host, DNS, storage and parameters, validated in CI.
- Backup and restore are tested before launch. Corpus versions allow rolling back a bad publish without a restore.
- Pinecone is rebuildable from Postgres chunks, so it is a searchable copy, not the system of record.
- Alerts: monthly budget, p95 latency per stage, verification-failure rate, refusal rate.
- Move to managed containers and a managed database only when uptime or traffic requires it; the architecture does not change.

## Not yet decided

Hosting provider, domain, and whether the model provider is hosted or self-hosted for real documents (ADR-004). Nothing is provisioned.
