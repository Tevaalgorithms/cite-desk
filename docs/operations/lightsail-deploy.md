# Deploying CiteDesk on Amazon Lightsail (MVP)

One Lightsail instance runs three containers (API, web app, Caddy proxy) with Docker Compose. See [`docs/architecture/deployment.md`](../architecture/deployment.md) for why, the cost estimate and the limits.

## What has and has not been tested

| Tested here (on a laptop with Docker) | Not tested (needs a real Lightsail instance and a domain) |
| --- | --- |
| Both images build; the stack starts; API, web app and proxy talk to each other | Creating the instance, static IP and firewall in the Lightsail console |
| The API runs against Postgres 16; data lands in Postgres | Automatic HTTPS certificate issuance for a real domain |
| All 17 browser checks pass through the proxy; `scripts/smoke.sh` passes | Memory and speed on the $12 plan (2 GB), which is a starting guess |
| Containers run as non-root; the proxy hides the server header | Backups and restores on Lightsail |

Treat the Lightsail-specific steps below as a checklist to confirm, not a verified procedure.

## Before you start

- A domain name you control (for HTTPS). Without one, the stack serves plain HTTP only, which is fine for a private trial but not for real use.
- Decide the database (see the deployment doc). The compose file's `local-db` profile starts a Postgres container on the same instance **for trials only**: its data lives in one Docker volume on one machine.
- **Do not load real confidential documents.** Sign-in is still the development token scheme, and the model-provider and retention decisions (ADR-004) are open. Use public or synthetic documents.

## Steps

1. **Create the instance.** In the Lightsail console create a Linux instance (Ubuntu LTS) on a plan with at least 2 GB of RAM (the $12 plan at the time of writing).
2. **Attach a static IP** so the address survives restarts, and point your domain's `A` record at it.
3. **Firewall:** allow HTTP (80) and HTTPS (443) from anywhere. Restrict SSH (22) to your own address.
4. **Install Docker and the Compose plugin** by following Docker's official instructions for your Ubuntu version (<https://docs.docker.com/engine/install/ubuntu/>).
5. **Get the code:**
   ```bash
   git clone https://github.com/Tevaalgorithms/cite-desk.git
   cd cite-desk
   ```
6. **Create the settings file** `.env` in the repository folder, readable only by you:
   ```bash
   umask 077
   cat > .env <<EOF2
   CITEDESK_SITE=handbook.example.com
   CITEDESK_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
   CITEDESK_JWT_DEV_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
   CITEDESK_MODELS=offline
   EOF2
   chmod 600 .env
   ```
   Replace the database URL with your database. For a trial you can use the bundled Postgres instead: add `--profile local-db` to the compose commands below, set `CITEDESK_LOCAL_DB_PASSWORD` in your shell, and use `postgresql+psycopg://postgres:THAT_PASSWORD@postgres:5432/citedesk`. `.env` is git-ignored: never commit it.
7. **Start it:**
   ```bash
   docker compose -f infrastructure/docker/compose.yml --env-file .env up -d --build
   ```
   The first build takes a few minutes.
8. **Check it:**
   ```bash
   scripts/smoke.sh https://handbook.example.com
   ```
9. **Create sign-in tokens** (development scheme; give each person a short-lived one):
   ```bash
   docker compose -f infrastructure/docker/compose.yml --env-file .env exec api citedesk token --user alice --role admin --hours 8
   ```
   Users paste the token on the sign-in screen. Replace this with your organization's sign-in (OIDC) before wider use; it is planned, not built.

## Updating and rolling back

```bash
git pull
docker compose -f infrastructure/docker/compose.yml --env-file .env up -d --build
scripts/smoke.sh https://handbook.example.com
```

To roll back, check out the previous commit or tag (`git checkout <tag>`) and run the same `up -d --build`. Published content has its own rollback: unpublish a document in the admin console.

## Operations notes

- **Logs:** `docker compose -f infrastructure/docker/compose.yml logs -f api`.
- **Backups are not designed yet.** Use your database's snapshot feature. For the bundled trial Postgres, `docker compose exec postgres pg_dump -U postgres citedesk > backup.sql` works but you must copy the file off the machine yourself.
- **Single instance:** a deploy restarts the containers, so expect a short outage. The in-memory rate limiter and the keyword index are per container; this is why the MVP runs one API container.
- **Vector search** currently uses an in-memory index rebuilt at startup, so published documents are re-embedded on every restart. Fine for a small handbook; the Pinecone adapter is planned.
- **Local models:** to bake in the embedding model and cross-encoder, build the API image with `--build-arg EXTRAS="--extra models"` and set `CITEDESK_MODELS=local`. Check memory use on the instance first.
