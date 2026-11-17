import { useCallback, useId, useState, type SyntheticEvent } from "react";

import { useBridge } from "../app/BridgeContext";
import { useLoad } from "../app/useLoad";
import { BackendError } from "../bridge/bridge";
import {
  addDirectoryGrant,
  listGrants,
  revokeGrant,
  searchAudit,
  verifyAudit,
} from "../bridge/trust";
import { Button, Empty, ErrorText, Planned, Section } from "../components/ui";

const TYPE_FILTERS = [
  ["", "All events"],
  ["task.", "Tasks"],
  ["action.", "Actions"],
  ["approval.", "Approvals"],
  ["policy.", "Policy"],
  ["auth.", "Authentication"],
  ["permission.", "Permissions"],
  ["settings.", "Settings"],
  ["recovery.", "Recovery"],
] as const;

function AuditLog({ ready }: { ready: boolean }) {
  const bridge = useBridge();
  const [prefix, setPrefix] = useState("");
  const [text, setText] = useState("");
  const [exportNote, setExportNote] = useState<string | null>(null);
  const searchId = useId();
  const filterId = useId();
  const entries = useLoad(
    ready,
    useCallback(
      () =>
        searchAudit(bridge, {
          type_prefix: prefix || undefined,
          text: text || undefined,
          limit: 200,
        }),
      [bridge, prefix, text],
    ),
  );
  const chain = useLoad(
    ready,
    useCallback(() => verifyAudit(bridge), [bridge]),
  );
  const exportAs = (format: "json" | "csv") => {
    setExportNote(null);
    bridge.saveAuditExport(format).then(
      (r) => {
        setExportNote(r.saved ? `Saved to ${r.saved}` : "Export cancelled.");
      },
      (err: unknown) => {
        setExportNote(err instanceof BackendError ? err.message : "Export failed.");
      },
    );
  };
  return (
    <Section
      title="Audit log"
      action={
        <div className="flex gap-2">
          <Button
            onClick={() => {
              exportAs("json");
            }}
          >
            Export JSON
          </Button>
          <Button
            onClick={() => {
              exportAs("csv");
            }}
          >
            Export CSV
          </Button>
        </div>
      }
    >
      <p className="mb-3 text-sm" role="status">
        {chain.state.kind === "ready" &&
          (chain.state.value.ok ? (
            <span className="text-ok">
              Chain intact · {chain.state.value.entries} entries verified
            </span>
          ) : (
            <span className="text-danger">
              Chain broken at entry {chain.state.value.first_bad_seq}: {chain.state.value.reason}
            </span>
          ))}
        <span className="ml-2 text-xs text-ink-subtle">
          Tamper evidence, not prevention: see SECURITY.md.
        </span>
      </p>
      {exportNote && <p className="mb-3 text-xs text-ink-muted">{exportNote}</p>}
      <div className="mb-3 flex flex-wrap gap-3">
        <label htmlFor={searchId} className="sr-only">
          Search the audit log
        </label>
        <input
          id={searchId}
          type="search"
          placeholder="Search events"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
          }}
          className="w-64 rounded-md border border-line-strong bg-surface-raised px-3 py-1.5 text-sm text-ink"
        />
        <label htmlFor={filterId} className="sr-only">
          Event type
        </label>
        <select
          id={filterId}
          value={prefix}
          onChange={(e) => {
            setPrefix(e.target.value);
          }}
          className="rounded-md border border-line-strong bg-surface-raised px-3 py-1.5 text-sm text-ink"
        >
          {TYPE_FILTERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      {entries.state.kind === "error" && <ErrorText>{entries.state.error.message}</ErrorText>}
      {entries.state.kind === "ready" &&
        (entries.state.value.entries.length === 0 ? (
          <Empty>No matching events.</Empty>
        ) : (
          <ol className="divide-y divide-line" aria-label="Audit events">
            {entries.state.value.entries.map((e) => (
              <li key={e.seq} className="py-2 text-sm">
                <details>
                  <summary className="flex cursor-pointer items-center gap-3">
                    <span className="w-10 font-mono text-xs text-ink-subtle">#{e.seq}</span>
                    <span className="font-mono text-xs text-ink-muted">{e.ts}</span>
                    <span className="text-ink">{e.type}</span>
                    <span className="text-xs text-ink-subtle">{e.actor}</span>
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded bg-canvas p-2 font-mono text-xs text-ink-muted">
                    {JSON.stringify(
                      { task_id: e.task_id, payload: e.payload, hash: e.hash },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </li>
            ))}
          </ol>
        ))}
    </Section>
  );
}

function DirectoryAccess({ ready }: { ready: boolean }) {
  const bridge = useBridge();
  const grants = useLoad(
    ready,
    useCallback(() => listGrants(bridge), [bridge]),
  );
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const fail = (err: unknown) => {
    setError(err instanceof BackendError ? err.message : "The request failed.");
  };
  const add = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!path.startsWith("/")) {
      setError("Enter an absolute folder path, for example /Users/you/Documents.");
      return;
    }
    setError(null);
    addDirectoryGrant(bridge, path).then(() => {
      setPath("");
      grants.reload();
    }, fail);
  };
  const dirs =
    grants.state.kind === "ready"
      ? grants.state.value.grants.filter((g) => g.scope_type === "directory")
      : [];
  return (
    <Section title="Directory access">
      <p className="mb-3 text-sm text-ink-muted">
        JARVIS may only touch files inside these folders. Symlinks and “..” are resolved before
        every check. The file tool that uses these grants arrives in v0.1 · M5.
      </p>
      {grants.state.kind === "ready" && dirs.length === 0 && <Empty>No folders granted.</Empty>}
      <ul className="mb-3 divide-y divide-line">
        {dirs.map((g) => (
          <li key={g.id} className="flex items-center justify-between py-2 text-sm">
            <span className="font-mono text-xs text-ink">{g.scope_value}</span>
            <Button
              tone="danger"
              onClick={() => {
                revokeGrant(bridge, g.id).then(grants.reload, fail);
              }}
            >
              Revoke
            </Button>
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="flex gap-2">
        <label htmlFor={inputId} className="sr-only">
          Folder to grant
        </label>
        <input
          id={inputId}
          value={path}
          onChange={(e) => {
            setPath(e.target.value);
          }}
          placeholder="/Users/you/Documents"
          className="w-96 rounded-md border border-line-strong bg-surface-raised px-3 py-1.5 font-mono text-xs text-ink"
        />
        <button
          type="submit"
          className="motion-base rounded-md border border-line-strong px-3 py-1.5 text-sm text-ink hover:bg-surface-raised"
        >
          Grant access
        </button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}

export function SecurityCenter({ ready }: { ready: boolean }) {
  return (
    <div className="flex flex-col gap-6">
      <AuditLog ready={ready} />
      <DirectoryAccess ready={ready} />
      <Planned name="Terminal policy and allowlist" when="v0.2 · M6" />
      <Planned name="Browser permissions" when="v0.3 · M8" />
      <Planned name="Screen Recording and microphone permissions" when="v0.3 · M9–M10" />
    </div>
  );
}
