/**
 * Shared header for the two credential cards on /token: the credential's own
 * name, what it is, and which report buttons stop working without it. The team
 * asked for both cards to say this in the same place (2026-11-17) — when a
 * button fails, the first question is "which key does that one need?".
 */
export function KeyCardHeader({
  name,
  what,
  uses,
}: {
  /** The credential as the team says it: "APIFY Token", "ANTHROPIC_API_KEY". */
  name: string;
  /** One line on what the service does for us. */
  what: string;
  /** Report functions that depend on this credential. */
  uses: string[];
}) {
  return (
    <div className="mb-3">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h2 className="font-mono text-base font-bold tracking-tight">{name}</h2>
        <span className="text-xs text-muted-foreground">{what}</span>
      </div>
      <div className="mt-1.5 text-xs text-muted-foreground">ใช้กับปุ่มในหน้ารีพอร์ต:</div>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {uses.map((u) => (
          <li
            key={u}
            className="rounded-full border border-border bg-muted/40 px-2.5 py-0.5 text-xs"
          >
            {u}
          </li>
        ))}
      </ul>
    </div>
  );
}
