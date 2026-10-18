"use client";

import { sentenceFor, splitAnswer } from "@/lib/citations";
import { refusalText } from "@/lib/messages";
import type { Answer, Citation } from "@/lib/types";

interface Props {
  answer: Answer;
  onOpenSource: (citation: Citation, sentence: string | null) => void;
}

export function AnswerCard({ answer, onOpenSource }: Props) {
  if (answer.refused) {
    const { title, body } = refusalText(answer.refusal_reason);
    return (
      <div className="bubble answer refusal" role="status">
        <strong>{title}</strong>
        <p>{body}</p>
      </div>
    );
  }

  return (
    <div className="bubble answer">
      <p>
        {splitAnswer(answer.text).map((segment, index) => {
          if (segment.kind === "text") return <span key={index}>{segment.text}</span>;
          const citation = answer.citations.find((c) => c.marker === segment.marker);
          if (!citation) return <span key={index}>[{segment.marker}]</span>;
          return (
            <button
              key={index}
              type="button"
              className="chip"
              aria-label={`Open source ${segment.marker}: ${citation.document_title}, ${citation.section_path}`}
              onClick={() => onOpenSource(citation, sentenceFor(answer.text, segment.marker))}
            >
              {segment.marker}
            </button>
          );
        })}
      </p>
      <ul className="sources" aria-label="Sources">
        {answer.citations.map((citation) => (
          <li key={citation.marker}>
            <button
              type="button"
              className="link"
              onClick={() => onOpenSource(citation, sentenceFor(answer.text, citation.marker))}
            >
              [{citation.marker}] {citation.document_title} › {citation.section_path}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
