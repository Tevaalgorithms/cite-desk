"use client";

import { useState, type FormEvent } from "react";
import type { DocumentInfo } from "@/lib/types";

interface Props {
  document: DocumentInfo;
  /** Saves the license. Resolves to true when it was accepted. */
  onSave: (document: DocumentInfo, license: string) => Promise<boolean>;
}

/** Shows a document's license, with a small inline form to add or correct it. */
export function LicenseCell({ document, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  const open = () => {
    setValue(document.license ?? "");
    setEditing(true);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    const saved = await onSave(document, value);
    setSaving(false);
    if (saved) setEditing(false);
  };

  if (!editing) {
    return (
      <div className="license">
        {document.license ?? <span className="warn">missing</span>}{" "}
        <button type="button" className="link" onClick={open}>
          {document.license ? "Edit" : "Add license"}
        </button>
      </div>
    );
  }

  return (
    <form className="license-edit" onSubmit={(event) => void submit(event)}>
      <label className="sr-only" htmlFor={`license-${document.id}`}>
        License for {document.title}
      </label>
      <input
        id={`license-${document.id}`}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="For example: CC0 or CC BY 4.0"
        autoFocus
      />
      <button type="submit" className="primary small-button" disabled={saving || !value.trim()}>
        Save
      </button>
      <button type="button" className="link" onClick={() => setEditing(false)}>
        Cancel
      </button>
    </form>
  );
}
