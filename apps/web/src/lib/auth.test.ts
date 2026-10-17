import { describe, expect, it } from "vitest";
import { sessionFromToken } from "./auth";

function token(claims: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${encode({ alg: "HS256" })}.${encode(claims)}.signature`;
}

describe("sessionFromToken", () => {
  it("reads the user and role from a valid token", () => {
    const session = sessionFromToken(token({ sub: "alice", role: "admin", exp: 2_000_000_000 }), 1_000);
    expect(session).toMatchObject({ user: "alice", role: "admin" });
  });

  it("rejects expired tokens", () => {
    expect(sessionFromToken(token({ sub: "a", role: "analyst", exp: 500 }), 1_000)).toBeNull();
  });

  it("rejects unknown roles, missing fields and garbage", () => {
    expect(sessionFromToken(token({ sub: "a", role: "root", exp: 2_000_000_000 }), 1_000)).toBeNull();
    expect(sessionFromToken(token({ role: "admin", exp: 2_000_000_000 }), 1_000)).toBeNull();
    expect(sessionFromToken("not-a-token")).toBeNull();
    expect(sessionFromToken("a.%%%.c")).toBeNull();
  });

  it("trims whitespace pasted around a token", () => {
    const raw = token({ sub: "bob", role: "analyst", exp: 2_000_000_000 });
    expect(sessionFromToken(`  ${raw}\n`, 1_000)?.token).toBe(raw);
  });
});
