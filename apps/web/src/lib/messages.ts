// Plain-language text for situations where there is no answer.

import { ApiError } from "./api";

const REFUSALS: Record<string, { title: string; body: string }> = {
  nothing_relevant_found: {
    title: "I couldn't find that in the handbook",
    body: "Nothing in the published documents matched your question closely enough. Try different words, or ask HR or your manager.",
  },
  could_not_verify_answer: {
    title: "I couldn't verify an answer",
    body: "I found related text but could not back up every statement with a source, so I'm not going to guess.",
  },
  empty_question: {
    title: "Ask a question",
    body: "Type a question about the handbook.",
  },
};

export function refusalText(reason: string | null): { title: string; body: string } {
  return (
    (reason ? REFUSALS[reason] : undefined) ?? {
      title: "I can't answer that",
      body: "I wasn't able to answer from the handbook.",
    }
  );
}

/** What to tell the user when a request fails. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your sign-in has expired. Please sign in again.";
    if (error.status === 403) return "Your role does not allow this.";
    if (error.status === 429) return "You're asking too quickly. Wait a moment and try again.";
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

export const EXAMPLE_QUESTIONS = [
  "How many vacation days do I get?",
  "When do I need to return my laptop?",
  "How much time off do I get when I have a baby?",
  "Can I work from home?",
];
