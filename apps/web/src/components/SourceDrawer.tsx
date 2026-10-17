"use client";

import { useEffect, useRef } from "react";
import { highlight } from "@/lib/citations";
import type { Citation } from "@/lib/types";

interface Props {
  citation: Citation;
  sentence: string | null;
  onClose: () => void;
}

/** A side panel that shows the passage behind a citation, with the cited sentence highlighted. */
export function SourceDrawer({ citation, sentence, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const { before, match, after } = highlight(citation.quote, sentence);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Source passage">
        <header>
          <div>
            <p className="muted small">Source [{citation.marker}]</p>
            <h2>{citation.document_title}</h2>
            <p className="muted">{citation.section_path}</p>
          </div>
          <button ref={closeRef} type="button" className="icon" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <blockquote data-testid="source-passage">
          {before}
          {match && <mark>{match}</mark>}
          {after}
        </blockquote>
        <p className="muted small">
          The highlighted sentence is the one the answer quotes. The rest is the surrounding text
          from the same section.
        </p>
      </aside>
    </>
  );
}
