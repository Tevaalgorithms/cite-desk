# Security Policy

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub's **Security → Report a vulnerability** feature on this repository. Do not open a public issue.

## Secrets

- Never commit API keys, tokens, passwords, private keys, `.env` files, Terraform state, or cloud credentials.
- Use `.env.example` with placeholders only; keep real values in a secrets manager for deployed environments.
- If a secret is committed by mistake, revoke and rotate it immediately — removing it from git history is not sufficient.

## Content

- Do not commit uploaded documents, scraped pages or anything under `data/raw` or `data/processed`.
- Do not load confidential or personal documents into a deployment until the model-provider and retention decisions in `docs/architecture/adrs.md` have been made on purpose.

## Scope

CiteDesk is an engineering project. It is not certified against any security standard and does not provide legal, HR or compliance advice.
