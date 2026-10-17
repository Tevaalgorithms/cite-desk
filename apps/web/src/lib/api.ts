// A thin, typed wrapper around the CiteDesk API. All calls need a sign-in token.

import type { Answer, AuditEntry, ChunkInfo, DocumentInfo, NewDocument } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  token: string,
  path: string,
  options: { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the API running?");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    // 422 validation errors carry a list; everything else a short string.
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // fall through to the generic message
  }
  return `Request failed (${response.status})`;
}

export const ask = (token: string, question: string) =>
  request<Answer>(token, "/v1/chat", { method: "POST", body: { question } });

export const listDocuments = (token: string) =>
  request<DocumentInfo[]>(token, "/v1/admin/documents");

export const addDocument = (token: string, document: NewDocument) =>
  request<DocumentInfo>(token, "/v1/admin/documents", { method: "POST", body: document });

export const importUrl = (
  token: string,
  body: { url: string; source_name: string; license: string | null },
) => request<DocumentInfo>(token, "/v1/admin/imports", { method: "POST", body });

export const previewDocument = (token: string, id: string) =>
  request<ChunkInfo[]>(token, `/v1/admin/documents/${id}/preview`);

export const publishDocument = (token: string, id: string) =>
  request<DocumentInfo>(token, `/v1/admin/documents/${id}/publish`, { method: "POST" });

export const unpublishDocument = (token: string, id: string) =>
  request<DocumentInfo>(token, `/v1/admin/documents/${id}/unpublish`, { method: "POST" });

export const auditLog = (token: string) => request<AuditEntry[]>(token, "/v1/admin/audit");
