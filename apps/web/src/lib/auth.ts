// Keeps the sign-in token for this browser tab. The server checks every request;
// reading the token here only decides what to show.

import type { Role } from "./types";

const KEY = "citedesk.token";

export interface Session {
  token: string;
  user: string;
  role: Role;
}

// Kept in memory too, so sign-in still works when the browser blocks sessionStorage.
let memoryToken: string | null = null;
const listeners = new Set<() => void>();

/** Call `listener` whenever the token is saved or cleared. Returns an unsubscribe function. */
export function subscribeToToken(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function saveToken(token: string): void {
  memoryToken = token;
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    // Storage can be blocked (private windows); the in-memory copy lasts until reload.
  }
  notify();
}

export function loadToken(): string | null {
  if (memoryToken) return memoryToken;
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function clearToken(): void {
  memoryToken = null;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // nothing to clear
  }
  notify();
}

/** Read the user and role from a token, or null if it is malformed or expired. */
export function sessionFromToken(token: string, nowSeconds = Date.now() / 1000): Session | null {
  const payload = token.trim().split(".")[1];
  if (!payload) return null;
  try {
    const padded = payload.replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(atob(padded)) as { sub?: string; role?: string; exp?: number };
    const isRole = claims.role === "analyst" || claims.role === "reviewer" || claims.role === "admin";
    if (!claims.sub || !isRole || typeof claims.exp !== "number") return null;
    if (claims.exp <= nowSeconds) return null;
    return { token: token.trim(), user: claims.sub, role: claims.role as Role };
  } catch {
    return null;
  }
}
