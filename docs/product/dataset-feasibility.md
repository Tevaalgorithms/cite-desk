# CiteDesk — Dataset Feasibility

**Status as of 2026-10-17:** nothing downloaded or ingested. The demo corpus is not chosen because reuse terms are not yet verified.

## Requirements for a demo corpus

- A real company handbook or policy set, large enough that it cannot be pasted into a prompt (target: hundreds of pages, thousands of chunks).
- Reuse terms that permit copying, indexing and quoting passages in citations.
- Changes over time, so refresh and versioning are exercised.

## Candidates

| Candidate | What it is | Status |
| --- | --- | --- |
| GitLab public handbook (`handbook.gitlab.com`) | A large public company handbook covering values, engineering, customer experience and more | **Terms unverified.** The handbook site states no terms in the page text read on 2026-10-17. Its source repository carries an MIT `LICENSE` file, but that was not confirmed to cover the handbook content. Check the handbook's contribution and license pages before ingesting |
| Other open company handbooks | Not yet searched | Pending |
| A small synthetic handbook | Generated for the project, labelled synthetic | Fallback; weakest evidence of real-world quality |

## Decision rule

A document set is ingested only when its license and terms URL are recorded in the source registry (see [`schemas/dataset-manifest.example.yaml`](../../schemas/dataset-manifest.example.yaml)) and an admin has marked it publishable. A source flagged `restricted` cannot be published.

## Corpus size

To be measured at the first ingest. In-process BM25 comfortably covers the expected size (thousands to tens of thousands of chunks).

## Open questions

1. Do the candidate handbook's terms allow indexing, quoting and republishing excerpts, and what attribution is required?
2. How often does the source change, and can it be fetched respectfully (robots.txt, rate limits)?
3. Should a second, differently styled document set be added so the evaluation does not overfit one writing style?
