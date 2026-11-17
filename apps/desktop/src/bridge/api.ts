import type { HealthResponse, Setting, SettingsResponse } from "@jarvis/contracts";

import { expectOk, type BackendBridge } from "./bridge";

export type { Setting };
export type Health = HealthResponse;

export async function getHealth(bridge: BackendBridge): Promise<Health> {
  return expectOk(await bridge.request<Health>("GET", "/v1/health"));
}

export async function listSettings(bridge: BackendBridge): Promise<Setting[]> {
  return expectOk(await bridge.request<SettingsResponse>("GET", "/v1/settings")).settings;
}

export async function updateSetting(
  bridge: BackendBridge,
  key: string,
  value: unknown,
): Promise<Setting> {
  return expectOk(
    await bridge.request<Setting>("PUT", `/v1/settings/${encodeURIComponent(key)}`, { value }),
  );
}
