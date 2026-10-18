"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";
import { replaceDocument } from "@/lib/api";
import { errorText } from "@/lib/messages";
import type { DocumentInfo, NewVersion } from "@/lib/types";

interface Props {
  token: string;
  document: DocumentInfo;
  onReplaced: () => void;
  onCancel: () => void;
}

function contentTypeOf(fileName: string): NewVersion["content_type"] {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
  if (lower.endsWith(".md")) return "markdown";
  return "text";
}

/** Swaps a published document for a new version. Title, source and license carry over. */
export function ReplaceDocumentForm({ token, document, onReplaced, onCancel }: Props) {
  const [content, setContent] = useState("");
  const [contentType, setContentType] = useState<NewVersion["content_type"]>("markdown");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const readFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setContent(await file.text());
    setContentType(contentTypeOf(file.name));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await replaceDocument(token, document.id, { content, content_type: contentType });
      onReplaced();
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" aria-label="Replace document" onSubmit={(event) => void submit(event)}>
      <h2>Replace: {document.title}</h2>
      <p className="muted small">
        The new version takes over in one step: questions see the old version until you submit and
        the new one right after, never both. The old version is kept as retired. The title, source
        and license carry over.
      </p>

      <label htmlFor="replace-file">File (optional)</label>
      <input id="replace-file" type="file" accept=".md,.txt,.html,.htm" onChange={(event) => void readFile(event)} />

      <label htmlFor="replace-content">Or paste the new text</label>
      <textarea id="replace-content" rows={6} value={content} onChange={(event) => setContent(event.target.value)} />

      <label htmlFor="replace-type">Format</label>
      <select
        id="replace-type"
        value={contentType}
        onChange={(event) => setContentType(event.target.value as NewVersion["content_type"])}
      >
        <option value="markdown">Markdown</option>
        <option value="html">HTML</option>
        <option value="text">Plain text</option>
      </select>

      <div className="row">
        <button type="submit" className="primary" disabled={busy || !content.trim()}>
          Replace now
        </button>
        <button type="button" className="link" onClick={onCancel}>
          Cancel
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
