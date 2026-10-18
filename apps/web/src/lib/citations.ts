// Turns an answer like "You get 20 days [1]." into pieces the page can render.

export type Segment = { kind: "text"; text: string } | { kind: "cite"; marker: number };

const MARKER = /\[(\d+)\]/g;

/** Split answer text into plain text and citation markers, in order. */
export function splitAnswer(text: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ kind: "text", text: text.slice(last, start) });
    segments.push({ kind: "cite", marker: Number(match[1]) });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ kind: "text", text: text.slice(last) });
  return segments;
}

/** The answer sentence that carries a marker, without the markers themselves. */
export function sentenceFor(text: string, marker: number): string | null {
  const sentences = text.split(/(?<=[.!?])\s+/);
  const found = sentences.find((s) => s.includes(`[${marker}]`));
  return found ? found.replace(MARKER, "").replace(/\s+([.!?])/g, "$1").trim() : null;
}

export interface Highlighted {
  before: string;
  match: string;
  after: string;
}

/** Find the cited sentence inside the passage, so the drawer can highlight it. */
export function highlight(passage: string, sentence: string | null): Highlighted {
  const clean = passage.replace(/\s+/g, " ").trim();
  if (!sentence) return { before: clean, match: "", after: "" };
  const target = sentence.replace(/[.!?]+$/, "");
  const at = clean.indexOf(target);
  if (at < 0) return { before: clean, match: "", after: "" };
  return {
    before: clean.slice(0, at),
    match: clean.slice(at, at + target.length),
    after: clean.slice(at + target.length),
  };
}
