# CiteDesk — Evaluation Strategy

Every pull request is scored on retrieval, answer quality and citations, and the build fails when a gate is missed. Deterministic checks catch most regressions for free; RAGAS and DeepEval add judged metrics on a small, cached set.

## What is implemented today

`citedesk eval-retrieval` (see the README) measures, without any API key:

- **Retrieval by stage:** keyword only, vector only, both fused, and fused + reranked. Reported as Recall@1, @3, @5 and MRR, split by question type (exact wording versus paraphrase).
- **Answers:** whether the right section was cited, refusals of unanswerable questions, and "confidently wrong" answers (cited the wrong section, or answered an unanswerable question).
- **Threshold calibration:** the top reranker score of every question, so the relevance threshold comes from data.
- **Gates:** `--check evals/baselines.json` exits 1 if recall, MRR or correct answers fall below the recorded floor, or if confidently-wrong answers rise above the recorded ceiling. The offline backend is gated in the normal test suite; the local backend is gated by `tests/models` and by a separate CI job.

Not implemented yet: RAGAS and DeepEval (they need an LLM judge and an API key), the 120-question golden set reviewed by a person, and the nightly ablation run. The sample sets are small (27, 12 and 12 questions), written by the same author as the handbook, and the handbook is synthetic, so they show that the pipeline works and which stage helps, not how it will perform on a real handbook.

## Measured results on the sample handbook

Real local models versus the offline stand-ins, final pipeline (fused + reranked), answerable questions:

| Question set | What it is | Backend | Right section first | In top 3 | Answered correctly | Cited wrong section or answered an unanswerable question |
| --- | --- | --- | --- | --- | --- | --- |
| `golden` (21 answerable, 6 not) | Used to calibrate the threshold, so optimistic | offline | 0.81 | 0.90 | 13 of 21 | 1 |
| | | local | 0.95 | 1.00 | 19 of 21 | 0 |
| `heldout` (8 answerable, 4 not) | Used for diagnosis, now a validation set | offline | 0.63 | 0.63 | 3 of 8 | 1 |
| | | local | 0.88 | 1.00 | 6 of 8 | 2 |
| `test` (8 answerable, 4 not) | Unseen, run once | offline | 0.88 | 0.88 | 2 of 8 | 0 |
| | | local | 1.00 | 1.00 | 8 of 8 | 1 |

Reading it: the real models clearly beat the stand-ins on finding the right section and on answering paraphrased questions. Both still sometimes answer an unanswerable question that is close to a covered topic (2 of 14 unanswerable questions across the local runs). Before reranking, plain vector search beat the fused keyword-plus-vector ranking on paraphrases (Recall@1 0.90 versus 0.81 on `golden`), and the reranker repaired that, which is why hybrid retrieval is only worth it with a reranker here.

## Setting up judged evaluation: what you need to provide

RAGAS and DeepEval score answers with a language model acting as judge. Nothing runs until these are decided:

| Item | Why | Status |
| --- | --- | --- |
| A judge-model API key | The judge is a paid model call. The OpenAI key you already have is enough for both tools | Key exists in `.env` and SSM |
| The key as a GitHub Actions secret (for example `OPENAI_API_KEY`) | CI cannot read your `.env` or SSM. Pull requests from forks never receive secrets, so they run only the free checks | Not added |
| One pinned judge model | Pinning keeps scores comparable between runs. A cheaper model is fine for pull requests, a stronger one for the nightly run | Not chosen |
| A monthly budget (suggested: $100) | Judged runs cost money. Two limits apply: a per-run cap on judge calls (`CITEDESK_EVAL_MAX_JUDGE_CALLS_PER_RUN`, 300 by default) and a monthly spending limit set in the OpenAI dashboard, which only you can set | Not set |
| Which changes trigger a judged run | To avoid paying on every pull request: only changes to retrieval, prompts, the writer, the verifier or the evaluation code | Proposed in this document |
| A person who reviews the golden questions | Judged scores are only as good as the questions and reference answers | Not assigned |

The cost figures in this document are estimates from third-party price pages and must be rechecked against your actual model before you set the budget.

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
