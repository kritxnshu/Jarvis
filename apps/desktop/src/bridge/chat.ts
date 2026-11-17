import type {
  ConversationList,
  ConversationView,
  HealthCheckView,
  MessageList,
  ProvidersResponse,
  ProviderView,
  RouteStepView,
  SendResult,
  StopResult,
} from "@jarvis/contracts";

import { expectOk, type BackendBridge } from "./bridge";

export async function listConversations(bridge: BackendBridge): Promise<ConversationList> {
  return expectOk(await bridge.request<ConversationList>("GET", "/v1/conversations"));
}

export async function createConversation(
  bridge: BackendBridge,
  title: string,
): Promise<ConversationView> {
  return expectOk(await bridge.request<ConversationView>("POST", "/v1/conversations", { title }));
}

export async function listMessages(bridge: BackendBridge, id: string): Promise<MessageList> {
  return expectOk(await bridge.request<MessageList>("GET", `/v1/conversations/${id}/messages`));
}

export async function sendMessage(
  bridge: BackendBridge,
  conversationId: string,
  text: string,
): Promise<SendResult> {
  return expectOk(
    await bridge.request<SendResult>("POST", `/v1/conversations/${conversationId}/messages`, {
      text,
    }),
  );
}

export async function stopMessage(bridge: BackendBridge, messageId: string): Promise<StopResult> {
  return expectOk(await bridge.request<StopResult>("POST", `/v1/messages/${messageId}/stop`));
}

export async function listProviders(bridge: BackendBridge): Promise<ProvidersResponse> {
  return expectOk(await bridge.request<ProvidersResponse>("GET", "/v1/providers"));
}

export async function updateProvider(
  bridge: BackendBridge,
  id: string,
  change: { base_url?: string; enabled?: boolean },
): Promise<ProviderView> {
  return expectOk(await bridge.request<ProviderView>("PUT", `/v1/providers/${id}`, change));
}

export async function saveCredential(
  bridge: BackendBridge,
  id: string,
  secret: string,
): Promise<ProviderView> {
  return expectOk(
    await bridge.request<ProviderView>("PUT", `/v1/providers/${id}/credential`, { secret }),
  );
}

export async function deleteCredential(bridge: BackendBridge, id: string): Promise<ProviderView> {
  return expectOk(
    await bridge.request<ProviderView>("POST", `/v1/providers/${id}/credential/delete`),
  );
}

export async function checkProvider(bridge: BackendBridge, id: string): Promise<HealthCheckView> {
  return expectOk(await bridge.request<HealthCheckView>("POST", `/v1/providers/${id}/check`));
}

export async function setRoute(
  bridge: BackendBridge,
  task: string,
  chain: RouteStepView[],
): Promise<ProvidersResponse> {
  return expectOk(await bridge.request<ProvidersResponse>("PUT", `/v1/routes/${task}`, { chain }));
}
