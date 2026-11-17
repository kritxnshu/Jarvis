-- Trust kernel (M2): tasks, actions, write-ahead intents, approvals, grants, audit, receipts.

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    state TEXT NOT NULL,
    state_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX tasks_state ON tasks(state);

CREATE TABLE actions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    tool TEXT NOT NULL,
    tool_version INTEGER NOT NULL,
    params_json TEXT NOT NULL,
    digest TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    risk TEXT NOT NULL,
    category TEXT,
    recovery TEXT,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    approval_id TEXT,
    output_json TEXT,
    error TEXT,
    verification_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX actions_task ON actions(task_id);
CREATE INDEX actions_state ON actions(state);

-- Written and committed BEFORE a side-effecting tool runs (ADR-0005).
CREATE TABLE action_intents (
    id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL REFERENCES actions(id),
    attempt INTEGER NOT NULL,
    digest TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    started_at TEXT NOT NULL
);
CREATE INDEX action_intents_action ON action_intents(action_id);

CREATE TABLE action_outcomes (
    intent_id TEXT PRIMARY KEY REFERENCES action_intents(id),
    action_id TEXT NOT NULL REFERENCES actions(id),
    outcome TEXT NOT NULL,          -- completed | failed | uncertain
    detail_json TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL REFERENCES actions(id),
    digest TEXT NOT NULL,
    category TEXT,
    highest_risk INTEGER NOT NULL,
    request_json TEXT NOT NULL,     -- what / why / service / data / consequences
    status TEXT NOT NULL,           -- pending | approved | rejected | expired | used
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    decided_at TEXT,
    native_confirmed INTEGER NOT NULL DEFAULT 0,
    used_at TEXT
);
CREATE INDEX approvals_status ON approvals(status);

CREATE TABLE permission_grants (
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,       -- directory | domain | command_class | tool
    scope_value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT
);

-- Append-only, hash-chained. Triggers make edits fail loudly; the chain makes any edit that
-- bypasses them detectable (tamper evidence, not prevention: see SECURITY.md).
CREATE TABLE audit_log (
    seq INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    actor TEXT NOT NULL,
    task_id TEXT,
    payload_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX audit_log_type ON audit_log(type);
CREATE INDEX audit_log_task ON audit_log(task_id);
CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TABLE receipts (
    task_id TEXT PRIMARY KEY REFERENCES tasks(id),
    receipt_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
