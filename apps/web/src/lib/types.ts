// Shapes returned by the CiteDesk API (see src/citedesk/domain/models.py).

export type Role = "analyst" | "reviewer" | "admin";

export interface Citation {
  marker: number;
  chunk_id: string;
  document_title: string;
  section_path: string;
  quote: string; // the cited passage
}

export interface Answer {
  question: string;
  text: string; // empty when refused
  citations: Citation[];
  refused: boolean;
  refusal_reason: string | null;
  corpus_version: number;
}

export type DocumentStatus = "draft" | "published" | "retired";

export interface DocumentInfo {
  id: string;
  title: string;
  source_name: string;
  source_url: string | null;
  license: string | null;
  terms_url: string | null;
  status: DocumentStatus;
  created_at: string;
  published_at: string | null;
}

export interface ChunkInfo {
  id: string;
  ordinal: number;
  section_path: string;
  text: string;
}

export interface AuditEntry {
  at: string;
  actor: string;
  action: string;
  target: string;
}

export interface ModelInfo {
  writer: "openai" | "extractive" | "custom";
  provider: string;
  model: string;
  description: string;
  retrieval: string;
}

export interface ModelHealth {
  state: "live" | "offline" | "error";
  detail: string;
  latency_ms: number | null;
  checked_at: string | null;
}

export interface ModelUsage {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
}

/** What GET /v1/model and POST /v1/model/check return. */
export interface ModelReport {
  info: ModelInfo;
  health: ModelHealth | null; // null until the connection has been checked
  usage: ModelUsage | null;
}

export interface NewDocument {
  title: string;
  content: string;
  content_type: "markdown" | "html" | "text";
  source_name: string;
  license: string | null;
}
