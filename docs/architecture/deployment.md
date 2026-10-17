# CiteDesk — Deployment

**Decision for the MVP:** run on a single **Amazon Lightsail** instance with Docker Compose, chosen for low, flat cost (ADR-015). ECS or another managed container service is a later option, not part of the MVP. Nothing is provisioned yet. The container images, the compose file and a post-deploy smoke test exist and were tested locally with Docker (see [`docs/operations/lightsail-deploy.md`](../operations/lightsail-deploy.md)); the Lightsail instance itself, HTTPS for a real domain and backups are untested.

Three environments, one container image per service, and the same pipeline that runs the evaluation gates also deploys.

| Environment | Purpose | Data and services |
| --- | --- | --- |
| Local | Development | `uv run`, a SQLite file, in-memory stand-ins for the vector index and models (see the README) |
| CI (GitHub Actions) | Gates on every pull request | Fixed corpus snapshot, in-memory vector store, cached judge calls. Today CI runs Ruff, mypy and pytest only |
| Production (MVP) | Users | One Lightsail instance running Docker Compose behind a TLS-terminating proxy, a Postgres database, a Pinecone index, secrets as described below |

## MVP hosting on Lightsail

### Instance size and cost

Prices are from [AWS's Lightsail pricing page](https://aws.amazon.com/lightsail/pricing/), read 2026-10-17. The page shows no effective date, so confirm current prices before budgeting. All amounts are USD per month, Linux/Unix with a public IPv4 address.

| Plan | RAM | vCPU | SSD | Data transfer | Use |
| --- | --- | --- | --- | --- | --- |
| $7 | 1 GB | 2 | 40 GB | 2 TB | Probably too small once the cross-encoder model is loaded (not measured) |
| **$12** | 2 GB | 2 | 60 GB | 3 TB | **Starting choice** for the API, in-process BM25 and a local cross-encoder |
| $24 | 4 GB | 2 | 80 GB | 4 TB | Next step if memory or latency measurements require it |

The starting size is a judgment, not a measurement. Measure memory use and answer latency in Phase 7 and resize if needed; Lightsail plans can be changed.

### Database

The relational data (documents, chunks, audit log, corpus version) needs a durable home that outlives the instance. Options, cheapest first:

| Option | Monthly cost | Notes |
| --- | --- | --- |
| External free-tier Postgres | $0 | Matches the earlier preference. The code is tested on Postgres 16, but no provider has been chosen and its limits (storage, pauses, connection counts) are **not yet checked** |
| Lightsail managed database | $15 for the smallest plan (1 GB RAM, 40 GB SSD) | The pricing page does not name the engine, so confirm that PostgreSQL is offered before choosing it |
| SQLite file on the instance | $0 | Works for one instance only and needs snapshots for backup. Acceptable as a first deployment, not for a second instance |

### Monthly infrastructure estimate

About **$12** for the instance, plus **$0 to $15** for the database, plus Pinecone (free tier is expected to cover the MVP corpus, to be confirmed) and model usage. Model and evaluation costs are separate and are estimated in the evaluation strategy. These are estimates from list prices, not a quote.

## Secrets on Lightsail

The earlier plan to read secrets from SSM Parameter Store assumes the host has an AWS identity (an IAM role), as ECS tasks and EC2 instances do. For Lightsail this is **not confirmed**: the only source found was a community answer saying Lightsail instances carry a fixed service role that cannot be customised, and AWS's own documentation was not found to settle it. The MVP therefore does not depend on it.

| Approach | Used when | Trade-off |
| --- | --- | --- |
| **Root-only environment file on the instance, written by the deploy job from GitHub Actions secrets** | MVP (chosen) | Simple. The secrets sit on the disk of one machine, readable only by the deploy user |
| IAM user with a least-privilege key that reads SSM | If you want SSM before moving to ECS | A long-lived key to protect and rotate |
| IAM task role plus SSM parameters mapped into the task definition | After a move to ECS or EC2 | No stored keys. This is the target for a production move |

Rules for any approach:
- The application only reads `CITEDESK_*` environment variables (see `config.py`), so it works with all three.
- Real values never appear in git, the Docker image, Terraform files or logs.
- Use separate keys per environment, and rotate a key immediately if it appears anywhere it should not.

## Delivery pipeline

1. **Pull request:** lint, types, tests, verifier tests, retrieval and judged gates, secret scan, dependency audit (only the first three exist today).
2. **Merge to main:** build and scan images, run the full evaluation, deploy only if every gate passes.
3. **Deploy to Lightsail:** the deploy job connects to the instance, writes the environment file, pulls the new images and runs `docker compose up -d`.
4. **Post-deploy:** health check, smoke questions (a lookup, a refusal), and rollback to the previous image tag on failure.

## Operations

- Infrastructure as code (Terraform) for the instance, static IP, firewall rules and DNS, validated in CI.
- Firewall: open only HTTPS (and SSH restricted to known addresses). The database accepts connections only from the instance.
- Backups: database snapshots on a schedule, and a restore test before launch. Corpus versions allow rolling back a bad publish without a restore.
- Pinecone is rebuildable from the stored chunks, so it is a searchable copy, not the system of record.
- Alerts: monthly budget, p95 latency per stage, verification-failure rate, refusal rate.
- Lightsail is a single point of failure: one instance means downtime during deploys and no automatic failover. This is accepted for the MVP.

## When to move to ECS

Move to managed containers when any of these is true: more than one instance is needed for traffic or availability, zero-downtime deploys are required, secrets must come from an IAM role, or compliance requires it. The application does not change, because it reads configuration from environment variables and talks to the database and vector index through interfaces.

## Not yet decided

Which Postgres to use (ADR-015), the domain name, and whether the model provider is hosted or self-hosted for real documents (ADR-004). Nothing is provisioned.
