import type {
  BackendResponse,
  BridgeErrorBody,
  BridgeEvent,
  HttpMethod,
  StatusView,
} from "./types";

/** The Rust commands the webview is allowed to call (capabilities/main.json). */
export interface BackendBridge {
  status(): Promise<StatusView>;
  request<T>(method: HttpMethod, path: string, body?: unknown): Promise<BackendResponse<T>>;
  subscribe(onEvent: (event: BridgeEvent) => void): Promise<void>;
  /** Shows a native macOS dialog; only the shell can attach the confirmation token. */
  confirmHighRiskApproval<T>(approvalId: string): Promise<BackendResponse<T>>;
  /** Saves an audit export through a native save dialog. `saved` is null if cancelled. */
  saveAuditExport(format: "json" | "csv"): Promise<{ saved: string | null }>;
}

export type InvokeFn = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
export type ChannelFactory = (onMessage: (event: BridgeEvent) => void) => unknown;

/** An error with a stable code, from the bridge or from a backend error body. */
export class BackendError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "BackendError";
  }
}

function isErrorBody(value: unknown): value is BridgeErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).code === "string" &&
    typeof (value as Record<string, unknown>).message === "string"
  );
}

function toBackendError(err: unknown): BackendError {
  if (err instanceof BackendError) return err;
  if (isErrorBody(err)) return new BackendError(err.code, err.message);
  return new BackendError("bridge_error", err instanceof Error ? err.message : String(err));
}

export function createBridge(invoke: InvokeFn, makeChannel: ChannelFactory): BackendBridge {
  return {
    async status() {
      try {
        return (await invoke("backend_status")) as StatusView;
      } catch (err) {
        throw toBackendError(err);
      }
    },
    async request<T>(method: HttpMethod, path: string, body?: unknown) {
      try {
        return (await invoke("backend_request", {
          method,
          path,
          body: body === undefined ? null : body,
        })) as BackendResponse<T>;
      } catch (err) {
        throw toBackendError(err);
      }
    },
    async subscribe(onEvent) {
      try {
        await invoke("subscribe_events", { onEvent: makeChannel(onEvent) });
      } catch (err) {
        throw toBackendError(err);
      }
    },
    async confirmHighRiskApproval<T>(approvalId: string) {
      try {
        return (await invoke("confirm_high_risk_approval", { approvalId })) as BackendResponse<T>;
      } catch (err) {
        throw toBackendError(err);
      }
    },
    async saveAuditExport(format) {
      try {
        return (await invoke("save_audit_export", { format })) as { saved: string | null };
      } catch (err) {
        throw toBackendError(err);
      }
    },
  };
}

/** Throws a BackendError for any non-2xx response, using the backend's error body. */
export function expectOk<T>(response: BackendResponse<T>): T {
  if (response.status >= 200 && response.status < 300) return response.body;
  const body = response.body as { error?: unknown } | null;
  if (body && isErrorBody(body.error)) {
    throw new BackendError(body.error.code, body.error.message, response.status);
  }
  throw new BackendError("http_error", `backend returned ${response.status}`, response.status);
}
