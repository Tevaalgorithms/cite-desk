# CiteDesk — Data Flow

Three flows: content in, a question answered, and a code change gated.

## Status

Flows 1 and 2 are implemented in `src/citedesk/` and driven today by the command line. The API, auth, rate limits, answer cache, saved conversations, router and agent loop, and LangSmith tracing are planned and are marked as such below. Flow 3 is only partly implemented (see its note).

## 1. Content in (admin)

```mermaid
flowchart TD
    A["1. Admin adds content<br/>file or URL import"] --> B["2. Parse and check<br/>safe fetch for URLs · text checks · duplicate check"]
    B --> C["3. Chunk by section<br/>each chunk keeps its section path"]
    C --> D["4. Save as a draft<br/>not searchable yet"]
    D --> E["5. Preview<br/>admin reviews the chunks"]
    E --> F{"6. License recorded?"}
    F -- no --> X["Publish refused"]
    F -- yes --> G["7. Embed and index vectors"]
    G --> H["8. Mark published<br/>corpus version +1 · audit log"]
```

| Step | What happens | Failure handling |
| --- | --- | --- |
| Add | Markdown, HTML or plain text from a file, or a web page by URL | Web pages with an unsupported content type are rejected. Local files with an unknown extension are read as plain text |
| Parse and check | URLs: http/https only, public IP addresses only, every redirect rechecked, size limit, robots.txt honoured. Text: pages with too little text (error and login pages) are rejected, duplicates are found by content hash | `UnsafeUrlError`, `FetchError`, `ParseError`, `DuplicateDocumentError` |
| Chunk | Sentence-aware chunks of at most about 1,200 characters, with one sentence of overlap inside long sections. Chunks never cross a section | A section with no text produces no chunk |
| Save as draft | Document and chunks are stored and an `add` audit entry is written | Nothing is searchable yet |
| Preview | The admin sees the chunks and their section paths | Planned: excluding single chunks |
| License gate | Publishing needs a recorded license (ADR-011) | `PublishBlockedError`, document stays a draft |
| Index | Chunk text is embedded and the vectors are upserted | If the upsert or the status change fails, the vectors are removed and the document stays a draft |
| Publish | Status, corpus version and audit entry change in one transaction | Unpublish removes the vectors, marks the document retired and bumps the version |

The keyword (BM25) index is **not** built by ingestion. The answer package rebuilds it on the next question after it sees a new corpus version, which keeps the two packages independent. Page numbers, chunk exclusion and PDF or DOCX parsing are planned.

## 2. A question answered (employee)

```mermaid
flowchart TD
    Q["1. Employee asks<br/>CLI today · chat UI planned"] --> V["2. Check the corpus version<br/>rebuild the keyword index if it changed"]
    V --> BM["3. BM25 keyword search<br/>top 20"]
    BM --> VS["4. Vector search<br/>top 20"]
    VS --> F["5. Fuse with Reciprocal Rank Fusion<br/>best 30"]
    F --> RR["6. Rerank, keep the best 6"]
    RR --> T{"7. Any passage at or above<br/>the relevance threshold (0.5)?"}
    T -- no --> R1["Refusal: nothing_relevant_found"]
    T -- yes --> G["8. Writer drafts the answer with [n] citations"]
    G --> C{"9. Citation verifier<br/>every sentence supported?"}
    C -- pass --> S["10. Answer with citations"]
    C -- "fail, first attempt" --> G2["Retry with the strict writer setting"]
    G2 --> C
    C -- "fail, second attempt" --> R2["Refusal: could_not_verify_answer"]
```

| Step | Detail |
| --- | --- |
| Corpus version | The answer package asks the repository for the current version and reloads published passages only when it changed |
| Retrieve | Keyword and vector search run one after the other over published chunks only. Vectors of content no longer published are ignored |
| Fuse and rerank | Reciprocal Rank Fusion on both lists, then the reranker scores each passage 0 to 1 |
| Relevance threshold | Passages below `min_relevance` (default 0.5) are dropped, so loosely matching text is refused rather than quoted |
| Write | The writer sees numbered passages and must mark each sentence. The offline default quotes the best sentence of each close match |
| Verify | Deterministic checks: every sentence cited, markers exist, quotes verbatim, numbers present in the cited passage, enough of the words supported |
| Respond | Pass: answer plus citations. A second failure: refusal. Each question gets its own flow run, with no shared state |

Planned and not built: a router that sends multi-step questions to a bounded agent loop, an exact-key answer cache, authentication and rate limits, saved conversations and feedback, and LangSmith traces.

## 3. A code change gated (developer)

```mermaid
flowchart TD
    P["1. Open a pull request"] --> L["2. Lint · strict types · unit tests<br/>secret scan · dependency audit"]
    L --> D["3. Deterministic checks<br/>retrieval recall · citation verifier<br/>on a fixed corpus snapshot"]
    D --> J{"Retrieval, prompt or<br/>evaluation paths changed?"}
    J -- no --> OK["Merge allowed"]
    J -- yes --> E["4. RAGAS + DeepEval<br/>36-question subset · pinned judge · cached"]
    E --> T{"All gates pass?"}
    T -- yes --> OK
    T -- no --> FAIL["Build fails<br/>metrics table posted on the PR"]
    OK --> NI["Nightly: full set + ablation ladder<br/>results to LangSmith"]
```

Pull requests from forks run only steps 1 to 3, because repository secrets are not shared with forks.

**Implemented today:** `.github/workflows/ci.yml` runs Ruff, strict mypy and pytest. The secret scan, dependency audit, retrieval metrics, RAGAS and DeepEval steps are planned.
