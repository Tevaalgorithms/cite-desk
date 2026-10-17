# CiteDesk — Data Flow

Three flows: content in, a question answered, and a code change gated.

## 1. Content in (admin)

```mermaid
flowchart TD
    A["1. Admin adds content<br/>upload PDF/MD/DOCX or import a URL"] --> B["2. Fetch and parse<br/>safe fetch · clean text · skip duplicates"]
    B --> C["3. Chunk with provenance<br/>page · section · source · license · last updated"]
    C --> D["4. Preview and publish<br/>admin approves; draft until then"]
    D --> E["5. Index<br/>Pinecone vectors · BM25 index · new corpus version"]
    E --> F["6. Audit<br/>who, what, when"]
```

| Step | What happens | Failure handling |
| --- | --- | --- |
| Add | Upload or URL import | Reject disallowed types and oversized files |
| Fetch and parse | http/https only; private and metadata addresses blocked; size and redirect limits; robots.txt honoured | Error and login pages are rejected by a minimum-text check; duplicates by content hash are flagged |
| Chunk | Section-aware chunks keep source, section path, page, offsets, license and date | Parse failures leave the document in draft with the error shown |
| Preview and publish | Admin can exclude chunks or the whole document | Nothing is retrievable until published |
| Index | Embeds and indexes chunks, rebuilds BM25, bumps the corpus version, which invalidates cached answers | A failed index leaves the previous version live |
| Rollback | One click restores the previous corpus version | Pinecone is rebuildable from Postgres chunks |

## 2. A question answered (employee)

```mermaid
flowchart TD
    Q["1. Employee asks in chat"] --> R["2. Router (LangGraph)<br/>simple · multi-step · refuse"]
    R --> BM["3a. BM25<br/>exact terms"]
    R --> VS["3b. Vector search<br/>Pinecone"]
    BM --> F["4. Fuse (RRF)"]
    VS --> F
    F --> RR["5. Cross-encoder rerank<br/>keep best 6 to 8"]
    RR --> G["6. Model writes answer with [n] citations"]
    G --> V{"7. Citation verifier<br/>every sentence supported?"}
    V -- pass --> S["8. Stream answer<br/>citation chips + source drawer"]
    V -- fail --> RT["Retry once with quotes only"]
    RT --> V2{"Verifier again"}
    V2 -- pass --> S
    V2 -- fail --> X["Honest refusal"]
    R -. multi-step .-> AG["Agent loop<br/>max 4 steps · 6 retrievals · 15 s"] -.-> BM
```

| Step | Detail |
| --- | --- |
| Router | Classifies the question: single lookup, multi-step, or out of scope. Out-of-scope questions get a short decline with no retrieval |
| Retrieve | BM25 and vector search run in parallel against published chunks only |
| Fuse and rerank | Reciprocal Rank Fusion on the union, cross-encoder on the top 30, keep 6 to 8 |
| Generate | The model sees numbered passages and must mark each sentence |
| Verify | Deterministic checks first, then a support check for paraphrases |
| Respond | Pass: stream with citations. Second failure: refuse and offer to flag a content gap |
| Record | LangSmith trace and a stored message record (question hash, chunk ids, verification result, versions) |

Cache: an exact-key answer cache keyed on normalized question, corpus version, and prompt and model versions. No semantic answer cache in the MVP.

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
