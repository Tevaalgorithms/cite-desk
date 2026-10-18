// Turns the server's model report into what the status bar shows.

import type { ModelReport } from "./types";

export type Tone = "good" | "warn" | "bad" | "neutral";

export interface Badge {
  tone: Tone;
  /** For example "Live · openai · gpt-5.4-nano". */
  text: string;
  /** Longer explanation for the tooltip. */
  tooltip: string;
  /** False when there is nothing to check (the built-in writer makes no remote calls). */
  canCheck: boolean;
}

const STATE_WORD = { live: "Live", offline: "Offline", error: "Unavailable" } as const;

export function describeModel(report: ModelReport): Badge {
  const { info, health, usage } = report;
  const identity = `${info.provider} · ${info.model}`;
  const lines = [info.description];
  if (info.retrieval) lines.push(info.retrieval);
  if (usage && usage.calls > 0) {
    lines.push(
      `Since the server started: ${usage.calls} calls, ${usage.prompt_tokens + usage.completion_tokens} tokens.`,
    );
  }
  if (health?.detail) lines.push(health.detail);
  const tooltip = lines.join("\n");
  const canCheck = info.writer === "openai";

  if (!health) return { tone: "warn", text: `Not checked · ${identity}`, tooltip, canCheck };
  if (health.state === "live") {
    return { tone: "good", text: `${STATE_WORD.live} · ${identity}`, tooltip, canCheck };
  }
  if (health.state === "error") {
    return { tone: "bad", text: `${STATE_WORD.error} · ${identity}`, tooltip, canCheck };
  }
  return { tone: "neutral", text: `${STATE_WORD.offline} · ${identity}`, tooltip, canCheck };
}
