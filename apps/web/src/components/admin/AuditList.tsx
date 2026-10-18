import type { AuditEntry } from "@/lib/types";

export function AuditList({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <p className="muted">Nothing recorded yet.</p>;
  return (
    <ul className="audit">
      {entries.map((entry, index) => (
        <li key={`${entry.at}-${index}`}>
          <time dateTime={entry.at}>{new Date(entry.at).toLocaleString()}</time>
          <span>
            <strong>{entry.actor}</strong> {entry.action} <code>{entry.target}</code>
          </span>
        </li>
      ))}
    </ul>
  );
}
