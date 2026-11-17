import type { PlannedPart } from "../screens/registry";

/** The honest state for anything not built yet: says what is coming and when. */
export function NotAvailable({ parts }: { parts: readonly PlannedPart[] }) {
  return (
    <section
      aria-labelledby="not-available-title"
      className="rounded-lg border border-line bg-surface p-6"
    >
      <h2 id="not-available-title" className="text-lg font-semibold text-ink">
        Not available yet
      </h2>
      <p className="mt-2 max-w-prose text-sm text-ink-muted">
        This screen has no working features in this build. Nothing here is simulated: each part
        appears once it is built and tested.
      </p>
      <ul className="mt-5 divide-y divide-line border-t border-line">
        {parts.map((part) => (
          <li key={part.name} className="flex items-center justify-between gap-4 py-3">
            <span className="text-sm text-ink">{part.name}</span>
            <span className="shrink-0 font-mono text-xs text-ink-subtle">
              {part.release} · {part.milestone}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
