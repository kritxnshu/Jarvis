import type { Health } from "../bridge/api";
import type { StatusView } from "../bridge/types";
import type { Loadable } from "../app/useBackend";

const LABELS: Record<StatusView["state"], string> = {
  starting: "Core starting…",
  ready: "Core connected",
  failed: "Core failed to start",
  stopped: "Core stopped",
};

const DOT: Record<StatusView["state"], string> = {
  starting: "bg-warn",
  ready: "bg-ok",
  failed: "bg-danger",
  stopped: "bg-ink-subtle",
};

export function StatusBar({ status, health }: { status: StatusView; health: Loadable<Health> }) {
  return (
    <footer
      role="status"
      aria-live="polite"
      className="flex h-8 items-center gap-3 border-t border-line bg-surface px-4 text-xs text-ink-muted"
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${DOT[status.state]}`} />
      <span>{LABELS[status.state]}</span>
      {status.detail && <span className="truncate text-danger">{status.detail}</span>}
      {status.state === "ready" && health.kind === "ready" && (
        <span className="ml-auto font-mono text-ink-subtle">
          core {health.value.version} · schema {health.value.schema_version}
        </span>
      )}
      {status.state === "ready" && health.kind === "error" && (
        <span className="ml-auto text-danger">health check failed: {health.error.code}</span>
      )}
    </footer>
  );
}
