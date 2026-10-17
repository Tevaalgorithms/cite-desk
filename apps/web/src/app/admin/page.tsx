"use client";

import { AdminConsole } from "@/components/admin/AdminConsole";
import { SessionGate } from "@/components/SessionGate";
import { Shell } from "@/components/Shell";

export default function AdminPage() {
  return (
    <SessionGate>
      {(session, signOut) => (
        <Shell session={session} active="admin" onSignOut={signOut}>
          {session.role === "admin" ? (
            <AdminConsole token={session.token} />
          ) : (
            <main className="center">
              <p role="alert">The admin console is for administrators.</p>
            </main>
          )}
        </Shell>
      )}
    </SessionGate>
  );
}
