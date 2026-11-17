import type {
  ApprovalView,
  AuditEntryView,
  ExecutionView,
  GrantView,
  Receipt,
  TaskView,
} from "@jarvis/contracts";

/** Builders for realistic trust-kernel payloads used by UI tests. */

export function receipt(over: Partial<Receipt> = {}): Receipt {
  return {
    task_id: "T1",
    objective: "Send the invoice to Priya",
    plan: [{ step: 1, tool: "fixture.send_message", parameters: { to: "priya" } }],
    actions: [
      {
        action_id: "A1",
        tool: "fixture.send_message",
        tool_version: 1,
        parameters: { to: "priya" },
        digest: "d".repeat(64),
        state: "uncertain",
        status_label: "Uncertain — outcome unknown",
        attempts: 1,
        approval_id: null,
        intents: [
          {
            intent_id: "I1",
            attempt: 1,
            idempotency_key: "K1",
            started_at: "2026-11-17T10:00:00.000Z",
            outcome: "uncertain",
            detail: { error: "TimeoutError" },
            finished_at: "2026-11-17T10:00:02.000Z",
          },
        ],
        verification: null,
        error: "TimeoutError",
      },
    ],
    tools_used: ["fixture.send_message"],
    files: [],
    commands: [],
    tests: [],
    errors_and_recovery: [{ action_id: "A1", attempt: 1, outcome: "uncertain" }],
    final_status: "needs_review",
    final_status_reason: "the outcome of an action is unknown",
    verification_evidence: [],
    outstanding_actions: [{ action_id: "A1", state: "uncertain" }],
    created_at: "2026-11-17T10:00:00.000Z",
    updated_at: "2026-11-17T10:00:02.000Z",
    ...over,
  };
}

export function task(over: Partial<TaskView> = {}): TaskView {
  return {
    id: "T1",
    objective: "Send the invoice to Priya",
    state: "needs_review",
    state_reason: "the outcome of an action is unknown",
    created_at: "2026-11-17T10:00:00.000Z",
    updated_at: "2026-11-17T10:00:02.000Z",
    ...over,
  };
}

export function approval(over: Partial<ApprovalView> = {}): ApprovalView {
  return {
    id: "01JAPPROVAL000000000000000",
    action_id: "A2",
    digest: "e".repeat(64),
    category: "external_action",
    highest_risk: false,
    request: {
      intent: "Record a fixture effect",
      why: "Acceptance test",
      service: "Local fixture server",
      data_affected: "One record",
      consequences: "A counter increases",
      parameters: { label: "x" },
    },
    status: "pending",
    created_at: "2026-11-17T10:00:00.000Z",
    expires_at: "2026-11-17T10:10:00.000Z",
    decided_at: null,
    native_confirmed: false,
    used_at: null,
    ...over,
  };
}

export function auditEntry(seq: number, type: string): AuditEntryView {
  return {
    seq,
    ts: `2026-11-17T10:00:0${String(seq)}.000Z`,
    type,
    actor: "system",
    task_id: "T1",
    payload: { n: seq },
    prev_hash: "0".repeat(64),
    hash: String(seq).repeat(64).slice(0, 64),
  };
}

export function grant(over: Partial<GrantView> = {}): GrantView {
  return {
    id: "01JGRANT000000000000000000",
    scope_type: "directory",
    scope_value: "/Users/me/Documents",
    expires_at: null,
    ...over,
  };
}

export function execution(over: Partial<ExecutionView> = {}): ExecutionView {
  return {
    task_id: "T1",
    action_id: "A1",
    task_state: "completed",
    action_state: "user_attested",
    approval_id: null,
    receipt: receipt(),
    ...over,
  };
}
