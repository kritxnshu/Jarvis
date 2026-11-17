import type { Receipt } from "@jarvis/contracts";

import { StatePill } from "./ui";

/** An execution receipt: only recorded facts, labelled with how they were established. */
export function ReceiptView({ receipt }: { receipt: Receipt }) {
  return (
    <div className="flex flex-col gap-4 text-sm">
      <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-1">
        <dt className="text-ink-subtle">Objective</dt>
        <dd className="text-ink">{receipt.objective}</dd>
        <dt className="text-ink-subtle">Final status</dt>
        <dd>
          <StatePill state={receipt.final_status} />
          {receipt.final_status_reason && (
            <span className="ml-2 text-ink-muted">— {receipt.final_status_reason}</span>
          )}
        </dd>
        <dt className="text-ink-subtle">Tools used</dt>
        <dd className="font-mono text-xs text-ink-muted">{receipt.tools_used.join(", ")}</dd>
      </dl>
      <ol className="flex flex-col gap-3">
        {receipt.actions.map((a, n) => (
          <li key={a.action_id} className="rounded-md border border-line p-3">
            <div className="flex items-center justify-between gap-4">
              <span className="text-ink">
                {n + 1}. <span className="font-mono text-xs">{a.tool}</span>
              </span>
              <span className="text-xs font-medium text-ink">{a.status_label}</span>
            </div>
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-ink-muted">
                Parameters, attempts and evidence
              </summary>
              <pre className="mt-2 overflow-x-auto rounded bg-canvas p-2 font-mono text-xs text-ink-muted">
                {JSON.stringify(
                  {
                    parameters: a.parameters,
                    attempts: a.intents,
                    verification: a.verification,
                    error: a.error,
                    digest: a.digest,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </li>
        ))}
      </ol>
      {receipt.outstanding_actions.length > 0 && (
        <p className="text-xs text-warn">
          Outstanding: {receipt.outstanding_actions.map((o) => o.state).join(", ")}
        </p>
      )}
    </div>
  );
}
