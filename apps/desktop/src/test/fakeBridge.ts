import type { ApprovalView, AuditEntryView, GrantView, TaskDetail } from "@jarvis/contracts";

import type { Setting } from "../bridge/api";
import { execution } from "./fakeTrust";
import { BackendError, type BackendBridge } from "../bridge/bridge";
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
  tasks: TaskDetail[] = [];
  approvals: ApprovalView[] = [];
  audit: AuditEntryView[] = [];
  grants: GrantView[] = [];
  chainOk = true;
  nativeDialogApproves = true;
  savedExports: string[] = [];
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
    const trust = this.trust(method, path, body);
    if (trust) return respond(trust[0], trust[1]);
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

  private trust(method: HttpMethod, path: string, body: unknown): [number, unknown] | null {
    if (method === "GET" && path === "/v1/tasks") {
      return [200, { tasks: this.tasks.map((t) => t.task) }];
    }
    const taskId = /^\/v1\/tasks\/([A-Z0-9]+)$/.exec(path)?.[1];
    if (method === "GET" && taskId) {
      const found = this.tasks.find((t) => t.task.id === taskId);
      return found ? [200, found] : [404, { error: { code: "unknown_task", message: "no" } }];
    }
    const reviewId = /^\/v1\/tasks\/([A-Z0-9]+)\/review$/.exec(path)?.[1];
    if (method === "POST" && reviewId) {
      this.tasks = this.tasks.filter((t) => t.task.id !== reviewId);
      return [200, execution()];
    }
    if (method === "GET" && path === "/v1/approvals") return [200, { approvals: this.approvals }];
    const decisionId = /^\/v1\/approvals\/([A-Z0-9]+)\/decision$/.exec(path)?.[1];
    if (method === "POST" && decisionId) {
      const approval = this.approvals.find((a) => a.id === decisionId);
      if (approval?.highest_risk) {
        return [403, { error: { code: "native_confirmation_required", message: "native" } }];
      }
      this.approvals = this.approvals.filter((a) => a.id !== decisionId);
      const approve = (body as { approve: boolean }).approve;
      return [200, execution({ task_state: approve ? "completed" : "cancelled" })];
    }
    if (method === "POST" && path === "/v1/audit/search") {
      const q = body as { type_prefix?: string; text?: string };
      const entries = this.audit.filter(
        (e) =>
          (!q.type_prefix || e.type.startsWith(q.type_prefix)) &&
          (!q.text || JSON.stringify(e).includes(q.text)),
      );
      return [200, { entries }];
    }
    if (method === "GET" && path === "/v1/audit/verify") {
      return [
        200,
        this.chainOk
          ? { ok: true, entries: this.audit.length, first_bad_seq: null, reason: null }
          : { ok: false, entries: this.audit.length, first_bad_seq: 2, reason: "entry changed" },
      ];
    }
    if (method === "GET" && path === "/v1/grants") return [200, { grants: this.grants }];
    if (method === "POST" && path === "/v1/grants") {
      const g = {
        id: "01JNEWGRANT000000000000000",
        scope_type: "directory",
        expires_at: null,
        scope_value: (body as { scope_value: string }).scope_value,
      };
      this.grants = [...this.grants, g];
      return [200, g];
    }
    const revokeId = /^\/v1\/grants\/([A-Z0-9]+)\/revoke$/.exec(path)?.[1];
    if (method === "POST" && revokeId) {
      this.grants = this.grants.filter((g) => g.id !== revokeId);
      return [200, { revoked: revokeId }];
    }
    return null;
  }

  confirmHighRiskApproval<T>(approvalId: string): Promise<BackendResponse<T>> {
    if (!this.nativeDialogApproves) {
      // createBridge converts the shell's error object into a BackendError.
      return Promise.reject(new BackendError("native_dialog_cancelled", "still pending"));
    }
    this.approvals = this.approvals.filter((a) => a.id !== approvalId);
    return Promise.resolve({ status: 200, body: execution({ action_state: "verified" }) as T });
  }

  saveAuditExport(format: "json" | "csv"): Promise<{ saved: string | null }> {
    const saved = `/Users/me/jarvis-audit.${format}`;
    this.savedExports.push(saved);
    return Promise.resolve({ saved });
  }

  subscribe(onEvent: (event: BridgeEvent) => void): Promise<void> {
    this.listeners.push(onEvent);
    return Promise.resolve();
  }

  emit(event: BridgeEvent): void {
    for (const l of this.listeners) l(event);
  }
}
