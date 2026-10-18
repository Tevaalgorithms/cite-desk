"use client";

import type { DocumentInfo } from "@/lib/types";
import { LicenseCell } from "./LicenseCell";

interface Props {
  documents: DocumentInfo[];
  busyId: string | null;
  onPreview: (document: DocumentInfo) => void;
  onPublish: (document: DocumentInfo) => void;
  onUnpublish: (document: DocumentInfo) => void;
  onSaveLicense: (document: DocumentInfo, license: string) => Promise<boolean>;
}

export function DocumentTable({
  documents,
  busyId,
  onPreview,
  onPublish,
  onUnpublish,
  onSaveLicense,
}: Props) {
  if (documents.length === 0) {
    return <p className="muted">No documents yet. Add one below.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Title</th>
            <th scope="col">Source</th>
            <th scope="col">License</th>
            <th scope="col">Status</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id}>
              <td>{document.title}</td>
              <td>{document.source_name}</td>
              <td>
                <LicenseCell document={document} onSave={onSaveLicense} />
              </td>
              <td>
                <span className={`status ${document.status}`}>{document.status}</span>
              </td>
              <td className="actions">
                <button type="button" className="link" onClick={() => onPreview(document)}>
                  Preview
                </button>
                {document.status === "published" ? (
                  <button
                    type="button"
                    className="link danger"
                    disabled={busyId === document.id}
                    onClick={() => onUnpublish(document)}
                  >
                    Unpublish
                  </button>
                ) : (
                  document.status === "draft" && (
                    <button
                      type="button"
                      className="link"
                      disabled={busyId === document.id}
                      onClick={() => onPublish(document)}
                    >
                      Publish
                    </button>
                  )
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
