# CiteDesk — Evaluation Strategy

Every pull request is scored on retrieval, answer quality and citations, and the build fails when a gate is missed. Deterministic checks catch most regressions for free; RAGAS and DeepEval add judged metrics on a small, cached set.

## Metrics and starting gates

These thresholds are **starting guesses**. They are calibrated on the first measured baseline and then ratcheted up, never loosened to make a failing run pass.

| Layer | Metric | Tool | Starting gate |
| --- | --- | --- | --- |
| Retrieval | Recall@5, MRR@10 against gold passages | Deterministic code | Recall@5 at least 0.85 |
| Retrieval | Context precision | RAGAS | At least 0.75 |
| Retrieval | Context recall | RAGAS | At least 0.80 |
| Generation | Faithfulness | RAGAS and DeepEval | At least 0.90 |
| Generation | Answer relevancy | RAGAS | At least 0.85 |
| Citations | Every sentence cited; quotes verbatim; numbers and names traceable | Deterministic verifier | 100% |
| Robustness | Planted prompt-injection documents change nothing | Deterministic tests plus DeepEval custom metric | 100% |
| Behaviour | Unanswerable questions are refused, not guessed | Deterministic plus DeepEval | At least 95% |
| Non-regression | No judged metric more than 0.03 below the main-branch baseline | Compared run | Required |

## Golden questions

About 120 questions, authored from the corpus with gold passage ids and reference answers, and reviewed by a person who knows the material before they count as release gates. Pull requests run a 36-question subset; the nightly run uses the full set.

- Single-fact lookups, including exact policy names and plain-language phrasing
- Multi-part questions that need several pages (these exercise the agent)
- Questions whose answer changed between document versions
- Unanswerable and out-of-scope questions
- Prompt-injection cases

See [`schemas/eval-case.example.json`](../../schemas/eval-case.example.json) for the case shape.

## Head-to-head and ablation ladder

Before building retrieval, about 30 handbook questions are asked to a plain chatbot and to a search engine, with no access to the handbook, and then to CiteDesk. The result is reported honestly, including questions where the plain chatbot does well.

The nightly run measures a fixed ladder on the same questions: no retrieval, BM25 only, vectors only, hybrid, hybrid plus rerank, plus the agent. A component stays in the product only if it improves a metric on the questions it targets.

## Pipeline in GitHub Actions

1. **Every PR, no secrets needed:** lint, strict types, unit tests, verifier tests, retrieval metrics on a fixed corpus snapshot with an in-memory vector store.
2. **PR touching retrieval, prompts, safety or evaluation paths:** the judged job runs RAGAS and DeepEval on the 36-question subset against a throwaway Pinecone namespace with a pinned judge model, temperature 0 and cached judgments.
3. **Gate:** fails below any absolute threshold or below baseline by more than the tolerance, then posts a metrics table on the PR and uploads the full report.
4. **Nightly:** the full set plus the ladder; results go to LangSmith experiments and the quality dashboard.
5. **Forks:** run only step 1, because secrets are not shared with them.

## Keeping judged evaluation affordable and stable

- Cache judge results by a hash of question, answer, contexts and judge version.
- Cap judge calls per run and per month; each run reports its estimated cost.
- Judges vary a little between runs, so gates use tolerance bands and a paired comparison with the baseline.

## Cost estimate (approximate, unverified)

Rough planning figures, to be replaced with real traces: a judged PR run of 36 questions is expected to cost a few dollars at most, and a nightly full run a few more. Monthly evaluation spend with path filters and cached judgments is expected in the low hundreds of dollars or less. Model prices were taken from third-party price pages and must be confirmed before budgeting.
