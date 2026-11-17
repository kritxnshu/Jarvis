import { useId, useState } from "react";

import type { Setting } from "../bridge/api";
import { BackendError } from "../bridge/bridge";
import type { Loadable } from "../app/useBackend";

type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "error"; message: string };

const REDUCED_MOTION_OPTIONS = [
  { value: "system", label: "Follow macOS" },
  { value: "on", label: "Reduce motion" },
  { value: "off", label: "Full motion" },
] as const;

function useSaver(save: (key: string, value: unknown) => Promise<void>) {
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const run = (key: string, value: unknown) => {
    setState({ kind: "saving" });
    save(key, value).then(
      () => {
        setState({ kind: "idle" });
      },
      (err: unknown) => {
        setState({
          kind: "error",
          message: err instanceof BackendError ? err.message : "Could not save the setting.",
        });
      },
    );
  };
  return [state, run] as const;
}

export function Preferences({
  settings,
  save,
}: {
  settings: Loadable<Setting[]>;
  save: (key: string, value: unknown) => Promise<void>;
}) {
  const [saveState, runSave] = useSaver(save);
  const motionId = useId();
  const statusBarId = useId();

  if (settings.kind === "loading") {
    return <p className="text-sm text-ink-muted">Loading settings…</p>;
  }
  if (settings.kind === "error") {
    return (
      <p role="alert" className="text-sm text-danger">
        Settings could not be loaded ({settings.error.code}): {settings.error.message}
      </p>
    );
  }
  const byKey = new Map(settings.value.map((s) => [s.key, s]));
  const motion = byKey.get("appearance.reduced_motion");
  const statusBar = byKey.get("appearance.show_status_bar");
  const busy = saveState.kind === "saving";

  return (
    <div className="flex max-w-xl flex-col gap-6">
      {motion && (
        <div className="flex flex-col gap-2">
          <label htmlFor={motionId} className="text-sm font-medium text-ink">
            Motion
          </label>
          <select
            id={motionId}
            disabled={busy}
            value={String(motion.value)}
            onChange={(e) => {
              runSave(motion.key, e.target.value);
            }}
            className="w-56 rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-sm text-ink"
          >
            {REDUCED_MOTION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-ink-subtle">{motion.description}</p>
        </div>
      )}
      {statusBar && (
        <div className="flex items-start gap-3">
          <input
            id={statusBarId}
            type="checkbox"
            disabled={busy}
            checked={statusBar.value === true}
            onChange={(e) => {
              runSave(statusBar.key, e.target.checked);
            }}
            className="mt-1 h-4 w-4 accent-accent"
          />
          <div>
            <label htmlFor={statusBarId} className="text-sm font-medium text-ink">
              Show status bar
            </label>
            <p className="text-xs text-ink-subtle">{statusBar.description}</p>
          </div>
        </div>
      )}
      <p aria-live="polite" className="min-h-5 text-xs">
        {saveState.kind === "saving" && <span className="text-ink-muted">Saving…</span>}
        {saveState.kind === "error" && (
          <span role="alert" className="text-danger">
            {saveState.message}
          </span>
        )}
      </p>
    </div>
  );
}
