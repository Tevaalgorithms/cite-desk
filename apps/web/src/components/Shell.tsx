"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { Session } from "@/lib/auth";
import { ModelStatusBar } from "./ModelStatusBar";

interface Props {
  session: Session;
  active: "chat" | "admin";
  onSignOut: () => void;
  children: ReactNode;
}

export function Shell({ session, active, onSignOut, children }: Props) {
  return (
    <div className="shell">
      <header className="topbar">
        <Link href="/" className="brand">
          CiteDesk
        </Link>
        <nav aria-label="Main">
          <Link href="/" aria-current={active === "chat" ? "page" : undefined}>
            Ask
          </Link>
          {session.role === "admin" && (
            <Link href="/admin" aria-current={active === "admin" ? "page" : undefined}>
              Admin
            </Link>
          )}
        </nav>
        <div className="who">
          <span className="badge">{session.role}</span>
          <span className="muted small">{session.user}</span>
          <button type="button" className="link" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>
      <ModelStatusBar token={session.token} />
      {children}
    </div>
  );
}
