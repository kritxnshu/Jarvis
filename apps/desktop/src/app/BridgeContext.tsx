import { createContext, useContext, type ReactNode } from "react";

import type { BackendBridge } from "../bridge/bridge";

const BridgeContext = createContext<BackendBridge | null>(null);

export function BridgeProvider({
  bridge,
  children,
}: {
  bridge: BackendBridge;
  children: ReactNode;
}) {
  return <BridgeContext.Provider value={bridge}>{children}</BridgeContext.Provider>;
}

export function useBridge(): BackendBridge {
  const bridge = useContext(BridgeContext);
  if (!bridge) throw new Error("useBridge must be used inside <BridgeProvider>");
  return bridge;
}
