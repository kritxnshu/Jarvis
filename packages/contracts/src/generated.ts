/* Generated from the backend's Pydantic models by packages/contracts/scripts/generate.mjs.
 * Do not edit by hand: run `pnpm --filter @jarvis/contracts generate`. */

export interface JarvisContracts {
  ApprovalList?: ApprovalList;
  ApprovalRequestText?: ApprovalRequestText;
  ApprovalView?: ApprovalView;
  AuditEntries?: AuditEntries;
  AuditEntryView?: AuditEntryView;
  ChainVerificationView?: ChainVerificationView;
  ChatMessageView?: ChatMessageView;
  ConversationCreate?: ConversationCreate;
  ConversationList?: ConversationList;
  ConversationView?: ConversationView;
  CredentialUpdate?: CredentialUpdate;
  ErrorBody?: ErrorBody;
  ErrorResponse?: ErrorResponse;
  EventEnvelope?: EventEnvelope;
  ExecutionView?: ExecutionView;
  GrantList?: GrantList;
  GrantView?: GrantView;
  HealthCheckView?: HealthCheckView;
  HealthResponse?: HealthResponse;
  IntentView?: IntentView;
  MessageList?: MessageList;
  OutstandingAction?: OutstandingAction;
  PlanStep?: PlanStep;
  ProviderUpdate?: ProviderUpdate;
  ProviderView?: ProviderView;
  ProvidersResponse?: ProvidersResponse;
  Receipt?: Receipt;
  ReceiptAction?: ReceiptAction;
  RouteStepView?: RouteStepView;
  RouteUpdate?: RouteUpdate;
  SendMessage?: SendMessage;
  SendResult?: SendResult;
  Setting?: Setting;
  SettingUpdate?: SettingUpdate;
  SettingsResponse?: SettingsResponse;
  StopResult?: StopResult;
  TaskDetail?: TaskDetail;
  TaskList?: TaskList;
  TaskView?: TaskView;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ApprovalList".
 */
export interface ApprovalList {
  approvals: ApprovalView[];
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ApprovalView".
 */
export interface ApprovalView {
  action_id: string;
  category: string | null;
  created_at: string;
  decided_at: string | null;
  digest: string;
  expires_at: string;
  highest_risk: boolean;
  id: string;
  native_confirmed: boolean;
  request: ApprovalRequestText;
  status: string;
  used_at: string | null;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ApprovalRequestText".
 */
export interface ApprovalRequestText {
  consequences: string;
  data_affected: string;
  intent: string;
  parameters: Record<string, unknown>;
  service: string;
  why: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "AuditEntries".
 */
export interface AuditEntries {
  entries: AuditEntryView[];
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "AuditEntryView".
 */
export interface AuditEntryView {
  actor: string;
  hash: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  seq: number;
  task_id: string | null;
  ts: string;
  type: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ChainVerificationView".
 */
export interface ChainVerificationView {
  entries: number;
  first_bad_seq: number | null;
  ok: boolean;
  reason: string | null;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ChatMessageView".
 */
export interface ChatMessageView {
  content: string;
  conversation_id: string;
  created_at: string;
  error: string | null;
  id: string;
  model: string | null;
  provider_id: string | null;
  role: string;
  status: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ConversationCreate".
 */
export interface ConversationCreate {
  title?: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ConversationList".
 */
export interface ConversationList {
  conversations: ConversationView[];
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ConversationView".
 */
export interface ConversationView {
  created_at: string;
  id: string;
  title: string;
  updated_at: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "CredentialUpdate".
 */
export interface CredentialUpdate {
  secret: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ErrorBody".
 */
export interface ErrorBody {
  code: string;
  message: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ErrorResponse".
 */
export interface ErrorResponse {
  error: ErrorBody;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "EventEnvelope".
 */
export interface EventEnvelope {
  id: string;
  payload: Record<string, unknown>;
  schema_version: number;
  task_id: string | null;
  ts: string;
  type: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ExecutionView".
 */
export interface ExecutionView {
  action_id: string;
  action_state: string;
  approval_id: string | null;
  receipt: Receipt;
  task_id: string;
  task_state: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "Receipt".
 */
export interface Receipt {
  actions: ReceiptAction[];
  commands: Record<string, unknown>[];
  created_at: string;
  errors_and_recovery: Record<string, unknown>[];
  files: Record<string, unknown>[];
  final_status: string;
  final_status_reason: string | null;
  objective: string;
  outstanding_actions: OutstandingAction[];
  plan: PlanStep[];
  task_id: string;
  tests: Record<string, unknown>[];
  tools_used: string[];
  updated_at: string;
  verification_evidence: Record<string, unknown>[];
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ReceiptAction".
 */
export interface ReceiptAction {
  action_id: string;
  approval_id: string | null;
  attempts: number;
  digest: string;
  error: string | null;
  intents: IntentView[];
  parameters: Record<string, unknown>;
  state: string;
  status_label: string;
  tool: string;
  tool_version: number;
  verification: Record<string, unknown> | null;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "IntentView".
 */
export interface IntentView {
  attempt: number;
  detail: Record<string, unknown> | null;
  finished_at: string | null;
  idempotency_key: string;
  intent_id: string;
  outcome: string | null;
  started_at: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "OutstandingAction".
 */
export interface OutstandingAction {
  action_id: string;
  state: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "PlanStep".
 */
export interface PlanStep {
  parameters: Record<string, unknown>;
  step: number;
  tool: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "GrantList".
 */
export interface GrantList {
  grants: GrantView[];
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "GrantView".
 */
export interface GrantView {
  expires_at: string | null;
  id: string;
  scope_type: string;
  scope_value: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "HealthCheckView".
 */
export interface HealthCheckView {
  detail: string;
  error_kind: string | null;
  models: string[];
  ok: boolean;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "HealthResponse".
 */
export interface HealthResponse {
  schema_version: number;
  status: string;
  version: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "MessageList".
 */
export interface MessageList {
  messages: ChatMessageView[];
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ProviderUpdate".
 */
export interface ProviderUpdate {
  base_url?: string | null;
  enabled?: boolean | null;
  key_optional?: boolean | null;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ProviderView".
 */
export interface ProviderView {
  base_url: string;
  configured: boolean;
  credential_hint: string | null;
  display_name: string;
  enabled: boolean;
  has_credential: boolean;
  id: string;
  key_optional: boolean;
  kind: string;
  retention_policy_url: string | null;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "ProvidersResponse".
 */
export interface ProvidersResponse {
  providers: ProviderView[];
  routes: {
    [k: string]: RouteStepView[];
  };
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "RouteStepView".
 */
export interface RouteStepView {
  model: string;
  provider_id: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "RouteUpdate".
 */
export interface RouteUpdate {
  chain: RouteStepView[];
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "SendMessage".
 */
export interface SendMessage {
  text: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "SendResult".
 */
export interface SendResult {
  message_id: string;
  user_message_id: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "Setting".
 */
export interface Setting {
  default: unknown;
  description: string;
  is_default: boolean;
  key: string;
  value: unknown;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "SettingUpdate".
 */
export interface SettingUpdate {
  value: unknown;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "SettingsResponse".
 */
export interface SettingsResponse {
  settings: Setting[];
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "StopResult".
 */
export interface StopResult {
  stopped: boolean;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "TaskDetail".
 */
export interface TaskDetail {
  receipt: Receipt;
  task: TaskView;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "TaskView".
 */
export interface TaskView {
  created_at: string;
  id: string;
  objective: string;
  state: string;
  state_reason: string | null;
  updated_at: string;
}
/**
 * This interface was referenced by `JarvisContracts`'s JSON-Schema
 * via the `definition` "TaskList".
 */
export interface TaskList {
  tasks: TaskView[];
}
