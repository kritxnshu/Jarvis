import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";

import type { BridgeEvent } from "../bridge/types";

type Listener = (event: BridgeEvent) => void;

/** Fans the single backend event stream out to whichever screens are listening. */
export class EventHub {
  private listeners = new Set<Listener>();

  emit(event: BridgeEvent): void {
    for (const l of this.listeners) l(event);
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
}

const HubContext = createContext<EventHub | null>(null);

export function EventHubProvider({ hub, children }: { hub: EventHub; children: ReactNode }) {
  return <HubContext.Provider value={hub}>{children}</HubContext.Provider>;
}

/** Calls `onEvent` for every backend event while the component is mounted. */
export function useEvents(onEvent: Listener): void {
  const hub = useContext(HubContext);
  const handler = useRef(onEvent);
  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);
  useEffect(() => {
    if (!hub) return;
    return hub.subscribe((e) => {
      handler.current(e);
    });
  }, [hub]);
}
