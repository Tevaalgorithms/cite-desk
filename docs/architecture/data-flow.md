# CiteDesk — Data Flow

Three flows: content in, a question answered, and a code change gated. The README has the system overview and the step-by-step sequence diagrams; this page is the same story as plain flowcharts, with the failure handling in tables.

## Status

Flows 1 and 2 are built and tested, through the web app, the API and the command line. Not built: company sign-in (OIDC), streaming answers, saved conversations and feedback, and the RAGAS and DeepEval steps of flow 3 (on hold). An agent loop was measured and deliberately not built (ADR-018).

## 1. Content in (admin)

```mermaid
flowchart TD
    A["1. Admin adds content<br/>a file, pasted text or a web address"] --> B["2. Parse and check<br/>safe fetch for URLs · too-little-text check · duplicate check"]
    B --> C["3. Chunk by section<br/>each chunk keeps its section path"]
    C --> D["4. Save as a draft<br/>audit entry: add · not searchable yet"]
    D --> E["5. Preview<br/>admin reviews the chunks"]
    E --> F{"6. License recorded?"}
    F -- no --> L["Admin adds or corrects the license<br/>audit entry: license"]
    L --> F
    F -- yes --> G["7. Embed the chunks and write the vectors<br/>waits until the index can read them back"]
    G --> H["8. Mark published<br/>corpus version +1 · audit entry"]
    G -- "write or status change fails" --> X["Vectors removed<br/>the document stays a draft"]
    H --> R{"9. A revised version arrives?"}
    R -- yes --> S["Replace: add the new version as a draft<br/>write its vectors, then in one transaction<br/>retire the old and publish the new"]
```

| Step | What happens | Failure handling |
| --- | --- | --- |
| Add | Markdown, HTML or plain text from a file or pasted text, or a web page by address. Through the API the admin role is required and requests are rate limited | Web pages with an unsupported content type are rejected. Local files with an unknown extension are read as plain text |
| Parse and check | URLs: http/https only, public IP addresses only, every redirect rechecked, size limit, robots.txt honoured. Text: pages with too little text (error and login pages) are rejected; duplicates are found by content hash | `UnsafeUrlError`, `FetchError`, `ParseError`, and a duplicate message that names the existing document |
| Chunk | Sentence-aware chunks of at most about 1,200 characters, with one sentence of overlap inside long sections. Chunks never cross a section. The admin's title wins over the title found in the file | A section with no text produces no chunk |
| Save as draft | Document and chunks are stored and an `add` audit entry is written | Nothing is searchable yet |
| Preview | The admin sees the chunks and their section paths | Excluding single chunks is not built |
| License gate | Publishing needs a recorded license (ADR-011). A missing one is added or corrected in the table (inline editor, `POST .../license`, or `citedesk license`) | The publish is refused with a clear message; the document stays a draft |
| Embed and write | Chunk text is embedded by the local model and the vectors are written to the vector index (in memory or Pinecone). Pinecone applies writes late, so the write waits until the vectors can be read back | If the write or the status change fails the vectors are removed and the document stays a draft |
| Publish | Status, corpus version and audit entry change in one transaction | Unpublish removes the vectors (and waits until they are gone), marks the document retired and bumps the version |
| Replace | A revised version of a published document is added (title, source and license carry over), its vectors are written, then one transaction retires the old and publishes the new (corpus version +1 once), then the old vectors are deleted (ADR-021) | Before the swap a failure removes the new vectors and the old version stays live. If only the old vectors cannot be deleted the swap stands: searches ignore them and the repair at start removes them |

The keyword (BM25) index is **not** built by ingestion. The answer package rebuilds it on the next question after it sees a new corpus version, which keeps the two packages independent and also stops remembered answers from being served. Page numbers, chunk exclusion and PDF or DOCX parsing are not built.

## 2. A question answered (employee)

```mermaid
flowchart TD
    Q["1. Employee asks<br/>web app · API · CLI"] --> V["2. Check the corpus version<br/>rebuild the keyword index if it changed"]
    V --> CA{"3. Asked before?<br/>same question, corpus and model"}
    CA -- yes --> HIT["Answer from the cache<br/>no model call, no trace"]
    CA -- no --> BM["4. BM25 keyword search<br/>top 20"]
    BM --> VS["5. Vector search<br/>top 20"]
    VS --> F["6. Fuse with Reciprocal Rank Fusion<br/>best 30"]
    F --> RR["7. Rerank with the cross-encoder<br/>keep the best 6"]
    RR --> T{"8. Any passage above<br/>the relevance threshold?"}
    T -- no --> R1["Refusal: nothing_relevant_found"]
    T -- yes --> W["9. Writer drafts the answer<br/>OpenAI or the built-in writer"]
    W -- "model unreachable" --> R2["Refusal: model_unavailable"]
    W -- "says the passages do not answer" --> R3["Refusal: passages_do_not_answer"]
    W -- "a draft with [n] citations" --> C{"10. Citation verifier<br/>every sentence supported?"}
    C -- pass --> S["11. Answer with citations"]
    C -- "fail, first attempt" --> W2["Retry with the strict instruction"]
    W2 --> C
    C -- "fail, second attempt" --> R4["Refusal: could_not_verify_answer"]
    S --> ST["12. Remember it in the cache"]
    R1 --> ST
    R3 --> ST
```

| Step | Detail |
| --- | --- |
| Corpus version | The answer package asks the database for the current version and reloads the published passages only when it changed |
| Cache | An exact-match, in-memory cache keyed on the question (case, spacing and end punctuation ignored), the corpus version and a label for the writer, model and threshold. Publishing, unpublishing or switching models therefore stops old answers from being served |
| Retrieve | Keyword and vector search run one after the other over published chunks only. Vectors of content no longer published are ignored, which also covers Pinecone's late deletes |
| Fuse and rerank | Reciprocal Rank Fusion on both lists, then the cross-encoder scores each passage |
| Relevance threshold | Passages below `min_relevance` are dropped, so loosely matching text is refused rather than quoted. The value is calibrated for the chosen models (about -10 on the cross-encoder's scale) |
| Write | The model sees the numbered passages and must end every sentence with the number of its passage. It is told to use only the passages and to reply `NO_ANSWER` when they do not contain the answer. The built-in writer instead quotes the best sentence of the best passage |
| Verify | Deterministic checks: every sentence cited, the markers exist, quotes are verbatim, numbers appear in the cited passage, enough of the words are supported |
| Respond | Pass: answer plus citations. Each question gets its own flow run with no shared state |
| Remember | Verified answers and the two refusals that follow from the documents are cached. A model outage and a failed verification are never cached, because they may succeed next time |
| Trace | With `CITEDESK_LANGSMITH_TRACING=true` each run is sent to LangSmith with its steps, timings and the model call. Off by default, because a trace contains the question and (unless hidden) the passages |

Not built: streaming answers, saved conversations and feedback, company sign-in. Through the API a request first passes the sign-in token check, the role check and the rate limit.

## 3. A code change gated (developer)

```mermaid
flowchart TD
    P["1. Push or open a pull request"] --> J["2. Seven jobs run in parallel"]
    J --> J1["check: Ruff, strict mypy, pytest"]
    J --> J2["web: lint, types, unit tests, build"]
    J --> J3["e2e: a real browser against a real API and web server"]
    J --> J4["postgres: the workflow on Postgres 16"]
    J --> J5["local-models: retrieval quality gates with the real models"]
    J --> J6["images: the Docker images build"]
    J --> J7["secrets: gitleaks over the whole history"]
    J1 & J2 & J3 & J4 & J5 & J6 & J7 --> G{"3. All seven green?"}
    G -- yes --> OK["Merge allowed"]
    G -- no --> FIX["Fix before merging"]
```

The quality gates compare the retrieval and answer metrics with `evals/baselines.json` and fail if recall, correct answers or multi-part coverage fall, or if confidently wrong answers rise. Tests that use the real OpenAI, Pinecone and LangSmith services run only on request (a few cents each) and never in CI. The dependency audit, the RAGAS and DeepEval gates, and a nightly full evaluation are not built.
