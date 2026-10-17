"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ask } from "@/lib/api";
import { EXAMPLE_QUESTIONS, errorText } from "@/lib/messages";
import { ApiError } from "@/lib/api";
import type { Answer, Citation } from "@/lib/types";
import { AnswerCard } from "./AnswerCard";
import { SourceDrawer } from "./SourceDrawer";

interface Props {
  token: string;
  onSessionExpired: () => void;
}

interface Turn {
  id: number;
  question: string;
  state: "loading" | "done" | "error";
  answer?: Answer;
  error?: string;
}

interface OpenSource {
  citation: Citation;
  sentence: string | null;
}

export function ChatView({ token, onSessionExpired }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [source, setSource] = useState<OpenSource | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const busy = turns.some((turn) => turn.state === "loading");

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const send = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    const id = Date.now();
    setDraft("");
    setTurns((current) => [...current, { id, question: text, state: "loading" }]);
    try {
      const answer = await ask(token, text);
      setTurns((current) =>
        current.map((turn) => (turn.id === id ? { ...turn, state: "done", answer } : turn)),
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onSessionExpired();
      setTurns((current) =>
        current.map((turn) =>
          turn.id === id ? { ...turn, state: "error", error: errorText(error) } : turn,
        ),
      );
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(draft);
  };

  return (
    <div className="chat">
      <div className="thread" aria-live="polite">
        {turns.length === 0 && (
          <section className="empty">
            <h1>Ask the handbook</h1>
            <p className="muted">
              Every sentence in an answer links to the passage it came from. If the handbook does
              not say, I will tell you.
            </p>
            <div className="examples">
              {EXAMPLE_QUESTIONS.map((question) => (
                <button key={question} type="button" className="example" onClick={() => void send(question)}>
                  {question}
                </button>
              ))}
            </div>
          </section>
        )}

        {turns.map((turn) => (
          <div key={turn.id} className="turn">
            <div className="bubble question">{turn.question}</div>
            {turn.state === "loading" && (
              <div className="bubble answer pending" role="status">
                Checking sources<span className="dots" aria-hidden="true" />
              </div>
            )}
            {turn.state === "error" && (
              <div className="bubble answer refusal" role="alert">
                {turn.error}
              </div>
            )}
            {turn.state === "done" && turn.answer && (
              <AnswerCard
                answer={turn.answer}
                onOpenSource={(citation, sentence) => setSource({ citation, sentence })}
              />
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <input
          id="question"
          value={draft}
          maxLength={1000}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask a question about the handbook"
          autoComplete="off"
        />
        <button type="submit" className="primary" disabled={busy || !draft.trim()}>
          Ask
        </button>
      </form>
      <p className="footnote muted small">
        General information from the handbook, not HR or legal advice. Check the cited source before
        you act on an answer.
      </p>

      {source && (
        <SourceDrawer citation={source.citation} sentence={source.sentence} onClose={() => setSource(null)} />
      )}
    </div>
  );
}
