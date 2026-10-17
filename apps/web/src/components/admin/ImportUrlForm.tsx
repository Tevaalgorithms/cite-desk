"use client";

import { useState, type FormEvent } from "react";
import { importUrl } from "@/lib/api";
import { errorText } from "@/lib/messages";

interface Props {
  token: string;
  onAdded: () => void;
}

export function ImportUrlForm({ token, onAdded }: Props) {
  const [url, setUrl] = useState("");
  const [source, setSource] = useState("");
  const [license, setLicense] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const document = await importUrl(token, {
        url,
        source_name: source,
        license: license.trim() || null,
      });
      setMessage({ ok: true, text: `Imported “${document.title}” as a draft.` });
      setUrl("");
      onAdded();
    } catch (error) {
      setMessage({ ok: false, text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={(event) => void submit(event)}>
      <h2>Import a web page</h2>
      <p className="muted small">
        Only public http/https pages are fetched. Check the site&apos;s terms before importing.
      </p>
      <label htmlFor="import-url">Page address</label>
      <input id="import-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} required />
      <div className="grid">
        <div>
          <label htmlFor="import-source">Source</label>
          <input id="import-source" value={source} onChange={(event) => setSource(event.target.value)} required />
        </div>
        <div>
          <label htmlFor="import-license">License</label>
          <input
            id="import-license"
            value={license}
            onChange={(event) => setLicense(event.target.value)}
            placeholder="Required before publishing"
          />
        </div>
      </div>
      <button type="submit" className="primary" disabled={busy || !url || !source}>
        Import as draft
      </button>
      {message && (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "ok" : "error"}>
          {message.text}
        </p>
      )}
    </form>
  );
}
