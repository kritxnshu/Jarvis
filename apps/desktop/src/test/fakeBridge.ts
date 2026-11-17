import type { Setting } from "../bridge/api";
import type { BackendBridge } from "../bridge/bridge";
import type { BackendResponse, BridgeEvent, HttpMethod, StatusView } from "../bridge/types";

/**
 * Test double for the Rust bridge. It models the backend's settings routes in memory so UI
 * tests exercise real request/response shapes; it is never part of a production build
 * (vitest only includes src/**\/*.test.* and their imports).
 */
export class FakeBridge implements BackendBridge {
  statusView: StatusView = { state: "ready", detail: null };
  calls: { method: HttpMethod; path: string; body: unknown }[] = [];
  failNextPut: { status: number; code: string; message: string } | null = null;
  private listeners: ((event: BridgeEvent) => void)[] = [];
  settings: Setting[] = [
    {
      key: "appearance.reduced_motion",
      value: "system",
      default: "system",
      description: "Reduce interface motion.",
      is_default: true,
    },
    {
      key: "appearance.show_status_bar",
      value: true,
      default: true,
      description: "Show the status bar.",
      is_default: true,
    },
  ];

  status(): Promise<StatusView> {
    return Promise.resolve(this.statusView);
  }

  request<T>(method: HttpMethod, path: string, body?: unknown): Promise<BackendResponse<T>> {
    this.calls.push({ method, path, body });
    const respond = (status: number, payload: unknown) =>
      Promise.resolve({ status, body: payload as T });
    if (method === "GET" && path === "/v1/health") {
      return respond(200, { status: "ok", version: "0.1.0.dev0", schema_version: 1 });
    }
    if (method === "GET" && path === "/v1/settings") {
      return respond(200, { settings: this.settings });
    }
    const key = /^\/v1\/settings\/(.+)$/.exec(path)?.[1];
    if (method === "PUT" && key) {
      if (this.failNextPut) {
        const f = this.failNextPut;
        this.failNextPut = null;
        return respond(f.status, { error: { code: f.code, message: f.message } });
      }
      const value = (body as { value: unknown }).value;
      this.settings = this.settings.map((s) =>
        s.key === key ? { ...s, value, is_default: false } : s,
      );
      const saved = this.settings.find((s) => s.key === key);
      return saved
        ? respond(200, saved)
        : respond(404, { error: { code: "unknown_setting", message: "no such setting" } });
    }
    // Mirrors Tauri, which rejects with the serialized BridgeError object.
    // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
    return Promise.reject({ code: "route_not_allowed", message: `${method} ${path}` });
  }

  subscribe(onEvent: (event: BridgeEvent) => void): Promise<void> {
    this.listeners.push(onEvent);
    return Promise.resolve();
  }

  emit(event: BridgeEvent): void {
    for (const l of this.listeners) l(event);
  }
}
