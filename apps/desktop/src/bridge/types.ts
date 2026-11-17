// Bridge-level types: produced by the Rust shell, not the Python backend.
// Backend payload types come from the generated contracts package.

export type BackendState = "starting" | "ready" | "failed" | "stopped";

export interface StatusView {
  state: BackendState;
  detail: string | null;
}

export interface BackendResponse<T = unknown> {
  status: number;
  body: T;
}

export interface BridgeErrorBody {
  code: string;
  message: string;
}

export type HttpMethod = "GET" | "PUT" | "POST";

/** Any event delivered on the bridge channel: backend envelopes or bridge notices. */
export interface BridgeEvent {
  type: string;
  id?: string;
  ts?: string;
  task_id?: string | null;
  schema_version?: number;
  payload?: Record<string, unknown>;
}
