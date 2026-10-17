# CiteDesk — Product Requirements

## Problem

Employees ask the same policy questions repeatedly (leave, expenses, equipment, security practices), and handbook search returns pages, not answers. A general chatbot answers fluently but cannot show where the answer comes from and does not know the organization's current text.

## Users

| Role | Job | Example |
| --- | --- | --- |
| Employee | Get a cited answer fast | "What do I need to do with my laptop when I leave?" |
| Content admin | Add, review, publish and roll back documents | Upload a revised expenses policy |
| Reviewer | Judge answers and write golden questions | Mark an answer correct, incorrect or incomplete |

## Features (MVP)

1. **Chat** with streaming answers, citation chips on every sentence and a source drawer that opens the exact passage.
2. **Hybrid retrieval**: BM25 plus vector search, fused, then reranked by a cross-encoder.
3. **Citation enforcement**: a verifier blocks uncited or unsupported sentences; one retry, then an honest refusal.
4. **Admin console**: upload files, import URLs, preview chunks, publish, unpublish, roll back, audit log.
5. **Quality dashboard**: latest RAGAS and DeepEval results with trend per commit and failing questions.
6. **Optional bounded agent** for multi-part questions, kept only if the evaluation shows a gain.
7. **Feedback**: thumbs up or down with an optional note, feeding the reviewer queue.

## Acceptance criteria

| Area | Criterion |
| --- | --- |
| Citations | 100% of sentences in shown answers carry a valid marker; quoted text and numbers appear in the cited passage |
| Refusal | Unanswerable questions in the golden set are refused at least 95% of the time |
| Retrieval | Recall@5 meets the calibrated gate on the golden set (starting guess 0.85) |
| Answer quality | Faithfulness, answer relevancy and context precision meet the calibrated gates |
| Admin | A published document becomes retrievable; unpublish and rollback remove it; unpublished drafts never appear in retrieval |
| CI | A change that lowers a gated metric below its threshold or baseline fails the build |
| Chat | Streaming works; a clicked citation opens the right passage; refusal and conflict states are designed screens |

## Non-goals

- HR, legal or compliance advice, or recording decisions.
- Per-document access control and multi-tenant isolation (a later extension; see ADR-006).
- Graph RAG, fine-tuning, multi-language support, live system integrations.
- Real confidential data.

## Success measures

- The head-to-head against a plain chatbot shows a measurable advantage on handbook-specific questions, or the scope is revisited.
- Gates are enforced on `main` with a stored baseline.
- Every answer can be replayed from its stored trace.
