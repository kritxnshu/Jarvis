import { Channel, invoke } from "@tauri-apps/api/core";

import { createBridge, type BackendBridge } from "./bridge";
import type { BridgeEvent } from "./types";

/** The production bridge: Tauri IPC to the Rust shell. */
export function createTauriBridge(): BackendBridge {
  return createBridge(
    (cmd, args) => invoke(cmd, args),
    (onMessage) => {
      const channel = new Channel<BridgeEvent>();
      channel.onmessage = onMessage;
      return channel;
    },
  );
}
