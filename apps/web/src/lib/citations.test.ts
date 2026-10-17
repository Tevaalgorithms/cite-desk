import { describe, expect, it } from "vitest";
import { highlight, sentenceFor, splitAnswer } from "./citations";

describe("splitAnswer", () => {
  it("separates text from citation markers in order", () => {
    expect(splitAnswer("You get 20 days [1]. Carry over 5 [2].")).toEqual([
      { kind: "text", text: "You get 20 days " },
      { kind: "cite", marker: 1 },
      { kind: "text", text: ". Carry over 5 " },
      { kind: "cite", marker: 2 },
      { kind: "text", text: "." },
    ]);
  });

  it("returns plain text unchanged", () => {
    expect(splitAnswer("No markers here.")).toEqual([{ kind: "text", text: "No markers here." }]);
  });

  it("handles empty text", () => {
    expect(splitAnswer("")).toEqual([]);
  });
});

describe("sentenceFor", () => {
  it("returns the sentence for a marker without markers or stray spaces", () => {
    const text = "You get 20 days of vacation [1]. Contractors get none [2].";
    expect(sentenceFor(text, 1)).toBe("You get 20 days of vacation.");
    expect(sentenceFor(text, 2)).toBe("Contractors get none.");
  });

  it("returns null for an unknown marker", () => {
    expect(sentenceFor("Hello [1].", 5)).toBeNull();
  });
});

describe("highlight", () => {
  const passage = "Full-time employees receive 20 days of paid vacation each year.\nUnused days carry over.";

  it("marks the cited sentence inside the passage", () => {
    const result = highlight(passage, "Full-time employees receive 20 days of paid vacation each year.");
    expect(result.before).toBe("");
    expect(result.match).toBe("Full-time employees receive 20 days of paid vacation each year");
    expect(result.after).toBe(". Unused days carry over.");
  });

  it("falls back to the whole passage when the sentence is not found", () => {
    expect(highlight(passage, "Something else entirely.").match).toBe("");
    expect(highlight(passage, null).before).toContain("Unused days");
  });
});
