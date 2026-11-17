import type {
  ApprovalView,
  AuditEntryView,
  ChatMessageView,
  ConversationView,
  GrantView,
  ProviderView,
  RouteStepView,
  TaskDetail,
} from "@jarvis/contracts";

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
  conversations: ConversationView[] = [];
  messages: ChatMessageView[] = [];
  providers: ProviderView[] = [
    {
      id: "ollama",
      kind: "ollama",
      display_name: "Ollama (local, free)",
      base_url: "http://127.0.0.1:11434",
      key_optional: true,
      enabled: true,
      has_credential: false,
      credential_hint: null,
      configured: true,
      retention_policy_url: null,
    },
    {
      id: "anthropic",
      kind: "anthropic",
      display_name: "Anthropic",
      base_url: "https://api.anthropic.com",
      key_optional: false,
      enabled: true,
      has_credential: false,
      credential_hint: null,
      configured: false,
      retention_policy_url: "https://www.anthropic.com/legal/privacy",
    },
  ];
  routes: Record<string, RouteStepView[]> = {
    chat: [{ provider_id: "ollama", model: "llama3.2" }],
  };
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
    const trust = this.trust(method, path, body) ?? this.chat(method, path, body);
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

  private chat(method: HttpMethod, path: string, body: unknown): [number, unknown] | null {
    const now = "2026-11-17T10:00:00.000Z";
    if (method === "GET" && path === "/v1/conversations") {
      return [200, { conversations: this.conversations }];
    }
    if (method === "POST" && path === "/v1/conversations") {
      const c = {
        id: `01JCONV${String(this.conversations.length).padStart(19, "0")}`,
        title: (body as { title: string }).title,
        created_at: now,
        updated_at: now,
      };
      this.conversations = [c, ...this.conversations];
      return [200, c];
    }
    const msgs = /^\/v1\/conversations\/([A-Z0-9]+)\/messages$/.exec(path)?.[1];
    if (msgs && method === "GET") {
      return [200, { messages: this.messages.filter((m) => m.conversation_id === msgs) }];
    }
    if (msgs && method === "POST") {
      const n = this.messages.length;
      const base = {
        conversation_id: msgs,
        provider_id: null,
        model: null,
        error: null,
        created_at: now,
      };
      this.messages = [
        ...this.messages,
        {
          ...base,
          id: `U${String(n)}`,
          role: "user",
          status: "complete",
          content: (body as { text: string }).text,
        },
        {
          ...base,
          id: `A${String(n)}`,
          role: "assistant",
          status: "streaming",
          content: "",
          provider_id: "ollama",
          model: "llama3.2",
        },
      ];
      return [200, { user_message_id: `U${String(n)}`, message_id: `A${String(n)}` }];
    }
    const stopId = /^\/v1\/messages\/([A-Z0-9]+)\/stop$/.exec(path)?.[1];
    if (stopId && method === "POST") {
      this.messages = this.messages.map((m) =>
        m.id === stopId ? { ...m, status: "interrupted", error: "stopped by the user" } : m,
      );
      return [200, { stopped: true }];
    }
    if (method === "GET" && path === "/v1/providers") {
      return [200, { providers: this.providers, routes: this.routes }];
    }
    const cred = /^\/v1\/providers\/([a-z]+)\/credential$/.exec(path)?.[1];
    if (cred && method === "PUT") {
      const secret = (body as { secret: string }).secret;
      this.providers = this.providers.map((p) =>
        p.id === cred
          ? {
              ...p,
              has_credential: true,
              configured: true,
              credential_hint: `••••${secret.slice(-4)}`,
            }
          : p,
      );
      return [200, this.providers.find((p) => p.id === cred)];
    }
    const checkId = /^\/v1\/providers\/([a-z]+)\/check$/.exec(path)?.[1];
    if (checkId && method === "POST") {
      return [
        200,
        { ok: false, detail: "Not configured", models: [], error_kind: "not_configured" },
      ];
    }
    const task = /^\/v1\/routes\/([a-z_]+)$/.exec(path)?.[1];
    if (task && method === "PUT") {
      this.routes = { ...this.routes, [task]: (body as { chain: RouteStepView[] }).chain };
      return [200, { providers: this.providers, routes: this.routes }];
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
