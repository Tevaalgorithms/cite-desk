"use client";

import { useEffect, useState } from "react";
import { checkModel, getModel } from "@/lib/api";
import { errorText } from "@/lib/messages";
import { describeModel } from "@/lib/modelBadge";
import type { ModelReport } from "@/lib/types";

// On page load a result up to 5 minutes old is fine; the button asks for a fresher one.
const ON_LOAD_MAX_AGE = 300;
const ON_CLICK_MAX_AGE = 15;

/** Shows which AI model writes the answers and whether it is working. */
export function ModelStatusBar({ token }: { token: string }) {
  const [report, setReport] = useState<ModelReport | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const known = await getModel(token);
        if (cancelled) return;
        setReport(known);
        // The model has never been checked: do it once now, so the bar shows a real state.
        if (known.health === null && known.info.writer === "openai") {
          setChecking(true);
          const checked = await checkModel(token, ON_LOAD_MAX_AGE);
          if (!cancelled) setReport(checked);
        }
      } catch (failure) {
        if (!cancelled) setProblem(errorText(failure));
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const check = async () => {
    setChecking(true);
    setProblem(null);
    try {
      setReport(await checkModel(token, ON_CLICK_MAX_AGE));
    } catch (failure) {
      setProblem(errorText(failure));
    } finally {
      setChecking(false);
    }
  };

  if (!report && !problem) {
    return <div className="modelbar" aria-busy="true" />;
  }
  if (!report) {
    return (
      <div className="modelbar">
        <span className="modelbar-label">AI model</span>
        <span className="pill bad">
          <span className="dot" aria-hidden="true" /> Unknown
        </span>
        <span className="muted small">{problem}</span>
      </div>
    );
  }

  const badge = describeModel(report);
  return (
    <div className="modelbar">
      <span className="modelbar-label">AI model</span>
      <span className={`pill ${badge.tone}`} title={badge.tooltip} data-testid="model-badge">
        <span className="dot" aria-hidden="true" /> {checking ? "Checking…" : badge.text}
      </span>
      {badge.canCheck && (
        <button type="button" className="outline" onClick={() => void check()} disabled={checking}>
          Check connection
        </button>
      )}
      {problem && <span className="muted small">{problem}</span>}
    </div>
  );
}
