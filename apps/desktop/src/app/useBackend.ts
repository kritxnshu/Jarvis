import { useCallback, useEffect, useRef, useState } from "react";

import { getHealth, listSettings, updateSetting, type Health, type Setting } from "../bridge/api";
import { BackendError } from "../bridge/bridge";
import type { BridgeEvent, StatusView } from "../bridge/types";
import { useBridge } from "./BridgeContext";

const STATUS_POLL_MS = 500;
const RESUBSCRIBE_MS = 1000;

export type Loadable<T> =
  { kind: "loading" } | { kind: "ready"; value: T } | { kind: "error"; error: BackendError };

function asBackendError(err: unknown): BackendError {
  return err instanceof BackendError
    ? err
    : new BackendError("unexpected", err instanceof Error ? err.message : String(err));
}

/** Backend lifecycle status, polled until it settles (ready / failed / stopped). */
export function useBackendStatus(): StatusView {
  const bridge = useBridge();
  const [status, setStatus] = useState<StatusView>({ state: "starting", detail: null });
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await bridge.status();
        if (cancelled) return;
        setStatus(next);
        if (next.state === "starting") timer = setTimeout(() => void poll(), STATUS_POLL_MS);
      } catch (err) {
        if (!cancelled) setStatus({ state: "failed", detail: asBackendError(err).message });
      }
    };
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [bridge]);
  return status;
}

export function useHealth(ready: boolean): Loadable<Health> {
  const bridge = useBridge();
  const [health, setHealth] = useState<Loadable<Health>>({ kind: "loading" });
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    getHealth(bridge).then(
      (value) => {
        if (!cancelled) setHealth({ kind: "ready", value });
      },
      (err: unknown) => {
        if (!cancelled) setHealth({ kind: "error", error: asBackendError(err) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [bridge, ready]);
  return health;
}

/** Subscribes to backend events while `ready`, resubscribing if the stream closes. */
export function useBackendEvents(ready: boolean, onEvent: (event: BridgeEvent) => void): void {
  const bridge = useBridge();
  const handler = useRef(onEvent);
  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);
  useEffect(() => {
    if (!ready) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const subscribe = () => {
      bridge
        .subscribe((event) => {
          if (!active) return;
          if (event.type === "bridge.stream_closed") {
            timer = setTimeout(subscribe, RESUBSCRIBE_MS);
            return;
          }
          handler.current(event);
        })
        .catch(() => {
          if (active) timer = setTimeout(subscribe, RESUBSCRIBE_MS);
        });
    };
    subscribe();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [bridge, ready]);
}

export interface SettingsState {
  settings: Loadable<Setting[]>;
  save: (key: string, value: unknown) => Promise<void>;
  applyRemoteChange: (key: string, value: unknown) => void;
}

export function useSettings(ready: boolean): SettingsState {
  const bridge = useBridge();
  const [settings, setSettings] = useState<Loadable<Setting[]>>({ kind: "loading" });

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    listSettings(bridge).then(
      (value) => {
        if (!cancelled) setSettings({ kind: "ready", value });
      },
      (err: unknown) => {
        if (!cancelled) setSettings({ kind: "error", error: asBackendError(err) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [bridge, ready]);

  const applyRemoteChange = useCallback((key: string, value: unknown) => {
    setSettings((prev) =>
      prev.kind === "ready"
        ? {
            kind: "ready",
            value: prev.value.map((s) => (s.key === key ? { ...s, value, is_default: false } : s)),
          }
        : prev,
    );
  }, []);

  const save = useCallback(
    async (key: string, value: unknown) => {
      const saved = await updateSetting(bridge, key, value);
      applyRemoteChange(saved.key, saved.value);
    },
    [bridge, applyRemoteChange],
  );

  return { settings, save, applyRemoteChange };
}

export function settingValue<T>(settings: Loadable<Setting[]>, key: string, fallback: T): T {
  if (settings.kind !== "ready") return fallback;
  const found = settings.value.find((s) => s.key === key);
  return found ? (found.value as T) : fallback;
}
