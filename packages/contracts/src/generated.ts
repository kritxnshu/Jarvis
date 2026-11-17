/* Generated from the backend's Pydantic models by packages/contracts/scripts/generate.mjs.
 * Do not edit by hand: run `pnpm --filter @jarvis/contracts generate`. */

export interface JarvisContracts {
  ErrorBody?: ErrorBody;
  ErrorResponse?: ErrorResponse;
  EventEnvelope?: EventEnvelope;
  HealthResponse?: HealthResponse;
  Setting?: Setting;
  SettingUpdate?: SettingUpdate;
  SettingsResponse?: SettingsResponse;
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
 * via the `definition` "HealthResponse".
 */
export interface HealthResponse {
  schema_version: number;
  status: string;
  version: string;
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
