import { useCallback, useEffect, useState } from "react";

import { BackendError } from "../bridge/bridge";
import type { Loadable } from "./useBackend";

/** Loads `fn` when `ready` and whenever `reload()` is called or `deps` change. */
export function useLoad<T>(
  ready: boolean,
  fn: () => Promise<T>,
): { state: Loadable<T>; reload: () => void } {
  const [state, setState] = useState<Loadable<T>>({ kind: "loading" });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => {
    setTick((t) => t + 1);
  }, []);
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    fn().then(
      (value) => {
        if (!cancelled) setState({ kind: "ready", value });
      },
      (err: unknown) => {
        if (cancelled) return;
        const error =
          err instanceof BackendError
            ? err
            : new BackendError("unexpected", err instanceof Error ? err.message : String(err));
        setState({ kind: "error", error });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [ready, fn, tick]);
  return { state, reload };
}
