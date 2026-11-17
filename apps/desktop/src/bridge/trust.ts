import type {
  ApprovalList,
  AuditEntries,
  ChainVerificationView,
  ExecutionView,
  GrantList,
  GrantView,
  TaskDetail,
  TaskList,
} from "@jarvis/contracts";

import { expectOk, type BackendBridge } from "./bridge";

export type ReviewChoice = "happened" | "retry" | "cancel";

export async function listTasks(bridge: BackendBridge): Promise<TaskList> {
  return expectOk(await bridge.request<TaskList>("GET", "/v1/tasks"));
}

export async function getTask(bridge: BackendBridge, taskId: string): Promise<TaskDetail> {
  return expectOk(await bridge.request<TaskDetail>("GET", `/v1/tasks/${taskId}`));
}

export async function reviewAction(
  bridge: BackendBridge,
  taskId: string,
  actionId: string,
  choice: ReviewChoice,
): Promise<ExecutionView> {
  return expectOk(
    await bridge.request<ExecutionView>("POST", `/v1/tasks/${taskId}/review`, {
      action_id: actionId,
      choice,
    }),
  );
}

export async function listApprovals(bridge: BackendBridge): Promise<ApprovalList> {
  return expectOk(await bridge.request<ApprovalList>("GET", "/v1/approvals"));
}

/** Approve or reject a regular approval. Highest-risk approvals must use confirmHighRisk. */
export async function decideApproval(
  bridge: BackendBridge,
  approvalId: string,
  approve: boolean,
): Promise<ExecutionView> {
  return expectOk(
    await bridge.request<ExecutionView>("POST", `/v1/approvals/${approvalId}/decision`, {
      approve,
    }),
  );
}

export async function confirmHighRisk(
  bridge: BackendBridge,
  approvalId: string,
): Promise<ExecutionView> {
  return expectOk(await bridge.confirmHighRiskApproval<ExecutionView>(approvalId));
}

export interface AuditQuery {
  type_prefix?: string | undefined;
  text?: string | undefined;
  task_id?: string | undefined;
  limit?: number | undefined;
}

export async function searchAudit(bridge: BackendBridge, q: AuditQuery): Promise<AuditEntries> {
  return expectOk(await bridge.request<AuditEntries>("POST", "/v1/audit/search", q));
}

export async function verifyAudit(bridge: BackendBridge): Promise<ChainVerificationView> {
  return expectOk(await bridge.request<ChainVerificationView>("GET", "/v1/audit/verify"));
}

export async function listGrants(bridge: BackendBridge): Promise<GrantList> {
  return expectOk(await bridge.request<GrantList>("GET", "/v1/grants"));
}

export async function addDirectoryGrant(bridge: BackendBridge, path: string): Promise<GrantView> {
  return expectOk(
    await bridge.request<GrantView>("POST", "/v1/grants", {
      scope_type: "directory",
      scope_value: path,
    }),
  );
}

export async function revokeGrant(bridge: BackendBridge, grantId: string): Promise<void> {
  expectOk(await bridge.request("POST", `/v1/grants/${grantId}/revoke`));
}
