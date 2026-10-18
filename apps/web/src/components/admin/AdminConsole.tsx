"use client";

import { useEffect, useState } from "react";
import {
  auditLog,
  listDocuments,
  previewDocument,
  publishDocument,
  setLicense,
  unpublishDocument,
} from "@/lib/api";
import { errorText } from "@/lib/messages";
import type { AuditEntry, ChunkInfo, DocumentInfo } from "@/lib/types";
import { AddDocumentForm } from "./AddDocumentForm";
import { AuditList } from "./AuditList";
import { DocumentTable } from "./DocumentTable";
import { ImportUrlForm } from "./ImportUrlForm";
import { ReplaceDocumentForm } from "./ReplaceDocumentForm";

export function AdminConsole({ token }: { token: string }) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [preview, setPreview] = useState<{ title: string; chunks: ChunkInfo[] } | null>(null);
  const [replacing, setReplacing] = useState<DocumentInfo | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Two separate messages: reloading the list must not erase the reason an action failed.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Bumping this number makes the effect below fetch everything again.
  const [reloads, setReloads] = useState(0);
  const refresh = () => setReloads((count) => count + 1);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [docs, entries] = await Promise.all([listDocuments(token), auditLog(token)]);
        if (cancelled) return;
        setDocuments(docs);
        setAudit(entries);
        setLoadError(null);
      } catch (failure) {
        if (!cancelled) setLoadError(errorText(failure));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, reloads]);

  const change = async (document: DocumentInfo, action: typeof publishDocument) => {
    setBusyId(document.id);
    setActionError(null);
    try {
      await action(token, document.id);
    } catch (failure) {
      setActionError(errorText(failure));
    } finally {
      setBusyId(null);
      refresh();
    }
  };

  /** Returns true when the license was saved, so the editor can close. */
  const saveLicense = async (document: DocumentInfo, license: string): Promise<boolean> => {
    setActionError(null);
    try {
      await setLicense(token, document.id, license);
      refresh();
      return true;
    } catch (failure) {
      setActionError(errorText(failure));
      return false;
    }
  };

  const showPreview = async (document: DocumentInfo) => {
    try {
      setPreview({ title: document.title, chunks: await previewDocument(token, document.id) });
    } catch (failure) {
      setActionError(errorText(failure));
    }
  };

  return (
    <main className="admin">
      <h1>Documents</h1>
      <p className="muted">
        New documents start as drafts and cannot be found by questions until you publish them.
        Publishing needs a recorded license.
      </p>
      {(loadError ?? actionError) && (
        <p role="alert" className="error">
          {loadError ?? actionError}
        </p>
      )}
      <DocumentTable
        documents={documents}
        busyId={busyId}
        onPreview={(document) => void showPreview(document)}
        onPublish={(document) => void change(document, publishDocument)}
        onUnpublish={(document) => void change(document, unpublishDocument)}
        onReplace={setReplacing}
        onSaveLicense={saveLicense}
      />

      {replacing && (
        <ReplaceDocumentForm
          token={token}
          document={replacing}
          onCancel={() => setReplacing(null)}
          onReplaced={() => {
            setReplacing(null);
            refresh();
          }}
        />
      )}

      {preview && (
        <section className="card" aria-label="Preview">
          <header className="row">
            <h2>Preview: {preview.title}</h2>
            <button type="button" className="link" onClick={() => setPreview(null)}>
              Close preview
            </button>
          </header>
          <p className="muted small">{preview.chunks.length} chunks, as they will be searched and cited.</p>
          <ol className="chunks">
            {preview.chunks.map((chunk) => (
              <li key={chunk.id}>
                <strong>{chunk.section_path}</strong>
                <p>{chunk.text}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="two-up">
        <AddDocumentForm token={token} onAdded={refresh} />
        <ImportUrlForm token={token} onAdded={refresh} />
      </div>

      <h2>Audit log</h2>
      <AuditList entries={audit} />
    </main>
  );
}
