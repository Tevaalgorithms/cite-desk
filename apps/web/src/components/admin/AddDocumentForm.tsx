"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";
import { addDocument } from "@/lib/api";
import { errorText } from "@/lib/messages";
import type { NewDocument } from "@/lib/types";

interface Props {
  token: string;
  onAdded: () => void;
}

function contentTypeOf(fileName: string): NewDocument["content_type"] {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
  if (lower.endsWith(".md")) return "markdown";
  return "text";
}

export function AddDocumentForm({ token, onAdded }: Props) {
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("");
  const [license, setLicense] = useState("");
  const [content, setContent] = useState("");
  const [contentType, setContentType] = useState<NewDocument["content_type"]>("markdown");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  // Changing this key replaces the file input, which forgets the chosen file.
  const [fileInputKey, setFileInputKey] = useState(0);

  const readFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setContent(await file.text());
    setContentType(contentTypeOf(file.name));
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, ""));
  };

  const reset = () => {
    setTitle("");
    setSource("");
    setLicense("");
    setContent("");
    setContentType("markdown");
    setFileInputKey((key) => key + 1);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const document = await addDocument(token, {
        title,
        content,
        content_type: contentType,
        source_name: source,
        license: license.trim() || null,
      });
      setMessage({ ok: true, text: `Added “${document.title}” as a draft. Review it, then publish.` });
      reset();
      onAdded();
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={(event) => void submit(event)}>
      <h2>Add a document</h2>
      <p className="muted small">Markdown, HTML or plain text. PDF is not supported yet.</p>

      <label htmlFor="doc-file">File (optional)</label>
      <input key={fileInputKey} id="doc-file" type="file" accept=".md,.txt,.html,.htm" onChange={(event) => void readFile(event)} />

      <label htmlFor="doc-content">Or paste the text</label>
      <textarea id="doc-content" rows={6} value={content} onChange={(event) => setContent(event.target.value)} />

      <div className="grid">
        <div>
          <label htmlFor="doc-title">Title</label>
          <input id="doc-title" value={title} onChange={(event) => setTitle(event.target.value)} required />
        </div>
        <div>
          <label htmlFor="doc-source">Source</label>
          <input id="doc-source" value={source} onChange={(event) => setSource(event.target.value)} required />
        </div>
        <div>
          <label htmlFor="doc-license">License</label>
          <input
            id="doc-license"
            value={license}
            onChange={(event) => setLicense(event.target.value)}
            placeholder="Required before publishing"
          />
        </div>
        <div>
          <label htmlFor="doc-type">Format</label>
          <select
            id="doc-type"
            value={contentType}
            onChange={(event) => setContentType(event.target.value as NewDocument["content_type"])}
          >
            <option value="markdown">Markdown</option>
            <option value="html">HTML</option>
            <option value="text">Plain text</option>
          </select>
        </div>
      </div>

      <button type="submit" className="primary" disabled={busy || !content.trim() || !title || !source}>
        Add as draft
      </button>
      {message && (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "ok" : "error"}>
          {message.text}
        </p>
      )}
    </form>
  );
}
