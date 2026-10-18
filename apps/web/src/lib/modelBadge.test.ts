import { describe, expect, it } from "vitest";
import { describeModel } from "./modelBadge";
import type { ModelReport } from "./types";

const openai = {
  writer: "openai" as const,
  provider: "openai",
  model: "gpt-5.4-nano",
  description: "A language model writes the answer.",
  retrieval: "Local embeddings.",
};

describe("describeModel", () => {
  it("shows a live remote model in the same shape as the other product", () => {
    const report: ModelReport = {
      info: openai,
      health: { state: "live", detail: "answered in 800 ms", latency_ms: 800, checked_at: "2026-10-18T00:00:00Z" },
      usage: { calls: 3, prompt_tokens: 900, completion_tokens: 60 },
    };
    const badge = describeModel(report);
    expect(badge.text).toBe("Live · openai · gpt-5.4-nano");
    expect(badge.tone).toBe("good");
    expect(badge.canCheck).toBe(true);
    expect(badge.tooltip).toContain("3 calls, 960 tokens");
    expect(badge.tooltip).toContain("answered in 800 ms");
  });

  it("warns when the connection has never been checked", () => {
    const badge = describeModel({ info: openai, health: null, usage: null });
    expect(badge.text).toBe("Not checked · openai · gpt-5.4-nano");
    expect(badge.tone).toBe("warn");
  });

  it("reports a failing model and keeps the reason", () => {
    const badge = describeModel({
      info: openai,
      health: { state: "error", detail: "OpenAI rejected the API key", latency_ms: null, checked_at: null },
      usage: null,
    });
    expect(badge.tone).toBe("bad");
    expect(badge.text).toBe("Unavailable · openai · gpt-5.4-nano");
    expect(badge.tooltip).toContain("rejected the API key");
  });

  it("describes the built-in writer as offline and has nothing to check", () => {
    const badge = describeModel({
      info: { writer: "extractive", provider: "built-in", model: "extractive quoting", description: "No language model.", retrieval: "" },
      health: { state: "offline", detail: "No language model in use", latency_ms: null, checked_at: null },
      usage: null,
    });
    expect(badge.text).toBe("Offline · built-in · extractive quoting");
    expect(badge.tone).toBe("neutral");
    expect(badge.canCheck).toBe(false);
  });
});
