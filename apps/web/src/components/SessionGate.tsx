"use client";

import { useMemo, useSyncExternalStore, type ReactNode } from "react";
import {
  clearToken,
  loadToken,
  saveToken,
  sessionFromToken,
  subscribeToToken,
  type Session,
} from "@/lib/auth";
import { SignIn } from "./SignIn";

interface Props {
  children: (session: Session, signOut: () => void) => ReactNode;
}

// While the page is being prepared on the server the token is unknown (undefined).
const tokenOnServer = (): string | null | undefined => undefined;

/** Shows the sign-in screen until there is a valid token, then renders the app. */
export function SessionGate({ children }: Props) {
  const token = useSyncExternalStore(subscribeToToken, loadToken, tokenOnServer);
  const session = useMemo(() => (token ? sessionFromToken(token) : null), [token]);

  const signIn = (value: string): boolean => {
    const next = sessionFromToken(value);
    if (next) saveToken(next.token);
    return next !== null;
  };

  if (token === undefined) return <main className="center muted">Loading…</main>;
  if (session === null) return <SignIn onSubmit={signIn} />;
  return <>{children(session, clearToken)}</>;
}
