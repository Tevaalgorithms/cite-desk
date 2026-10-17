"use client";

import { useState, type FormEvent } from "react";

interface Props {
  /** Returns true if the token was accepted. */
  onSubmit: (token: string) => boolean;
}

export function SignIn({ onSubmit }: Props) {
  const [token, setToken] = useState("");
  const [failed, setFailed] = useState(false);

  const handle = (event: FormEvent) => {
    event.preventDefault();
    setFailed(!onSubmit(token));
  };

  return (
    <main className="center">
      <form className="card signin" onSubmit={handle}>
        <h1>CiteDesk</h1>
        <p className="muted">Answers from your handbook, with the source for every sentence.</p>

        <label htmlFor="token">Sign-in token</label>
        <textarea
          id="token"
          rows={4}
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Paste your token"
          spellCheck={false}
          aria-invalid={failed}
          aria-describedby="token-help"
        />
        {failed && (
          <p role="alert" className="error">
            That token is not valid or has expired.
          </p>
        )}
        <button type="submit" className="primary" disabled={!token.trim()}>
          Sign in
        </button>

        <p id="token-help" className="muted small">
          Development sign-in: create a token with{" "}
          <code>uv run citedesk token --user you --role analyst</code> (use <code>--role admin</code>{" "}
          for the admin console). Production will use your organization&apos;s sign-in.
        </p>
      </form>
    </main>
  );
}
