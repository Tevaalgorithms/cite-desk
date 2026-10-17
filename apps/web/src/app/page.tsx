"use client";

import { ChatView } from "@/components/ChatView";
import { SessionGate } from "@/components/SessionGate";
import { Shell } from "@/components/Shell";

export default function ChatPage() {
  return (
    <SessionGate>
      {(session, signOut) => (
        <Shell session={session} active="chat" onSignOut={signOut}>
          <ChatView token={session.token} onSessionExpired={signOut} />
        </Shell>
      )}
    </SessionGate>
  );
}
