import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { BridgeProvider } from "../app/BridgeContext";
import { EventHub, EventHubProvider } from "../app/EventHub";
import { FakeBridge } from "../test/fakeBridge";
import { CommandCenter } from "./CommandCenter";
import { ProviderSettings } from "./ProviderSettings";

const FAKE_KEY = ["sk", "ant-secret-value-1234"].join("-"); // fake, split so it is never a literal key

function article(el: HTMLElement): HTMLElement {
  const found = el.closest("article");
  if (!found) throw new Error("not inside an article");
  return found;
}

function mount(ui: React.ReactElement, bridge: FakeBridge, hub = new EventHub()) {
  render(
    <BridgeProvider bridge={bridge}>
      <EventHubProvider hub={hub}>{ui}</EventHubProvider>
    </BridgeProvider>,
  );
  return { user: userEvent.setup(), hub };
}

describe("Command Center", () => {
  it("sends a message, streams deltas live and stops mid-response", async () => {
    const bridge = new FakeBridge();
    const { user, hub } = mount(<CommandCenter ready />, bridge);
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    const box = await screen.findByLabelText("Message");
    await user.type(box, "Hello there");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Hello there")).toBeTruthy();
    const [conv] = bridge.conversations;
    if (!conv) throw new Error("no conversation was created");
    act(() => {
      hub.emit({
        type: "chat.delta",
        payload: { conversation_id: conv.id, message_id: "A0", text: "Hi " },
      });
      hub.emit({
        type: "chat.delta",
        payload: { conversation_id: conv.id, message_id: "A0", text: "Priya" },
      });
    });
    expect(await screen.findByText("Hi Priya")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(bridge.calls).toContainEqual({
      method: "POST",
      path: "/v1/messages/A0/stop",
      body: undefined,
    });
    expect(await screen.findByText(/Interrupted — stopped by the user/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
  });

  it("keeps deltas that arrive before the new message is loaded (no lost first words)", async () => {
    const bridge = new FakeBridge();
    const { user, hub } = mount(<CommandCenter ready />, bridge);
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    await user.type(await screen.findByLabelText("Message"), "Hi");
    const [conv] = bridge.conversations;
    if (!conv) throw new Error("no conversation was created");
    act(() => {
      // The backend streams immediately; the UI has not reloaded the message list yet.
      hub.emit({
        type: "chat.delta",
        payload: { conversation_id: conv.id, message_id: "A0", text: "Hello" },
      });
    });
    await user.click(screen.getByRole("button", { name: "Send" }));
    act(() => {
      hub.emit({
        type: "chat.delta",
        payload: { conversation_id: conv.id, message_id: "A0", text: ", Priya." },
      });
    });
    expect(await screen.findByText("Hello, Priya.")).toBeTruthy();
  });

  it("ignores events from other conversations", async () => {
    const bridge = new FakeBridge();
    const { user, hub } = mount(<CommandCenter ready />, bridge);
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    await user.type(await screen.findByLabelText("Message"), "Q");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Q");
    act(() => {
      hub.emit({
        type: "chat.delta",
        payload: { conversation_id: "OTHER", message_id: "A0", text: "leak" },
      });
    });
    expect(screen.queryByText(/leak/)).toBeNull();
  });
});

describe("Provider Settings", () => {
  it("shows configuration honestly and never shows a saved key", async () => {
    const bridge = new FakeBridge();
    const { user } = mount(<ProviderSettings ready />, bridge);
    const card = article(await screen.findByRole("heading", { name: "Anthropic" }));
    expect(within(card).getByText("Not configured")).toBeTruthy();
    const input = within(card).getByLabelText("Anthropic API key");
    await user.type(input, FAKE_KEY);
    await user.click(within(card).getByRole("button", { name: "Save to Keychain" }));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("Saved key ••••1234")).toBeTruthy();
    });
    expect(screen.getByPlaceholderText<HTMLInputElement>("Saved key ••••1234").value).toBe("");
    expect(document.body.textContent).not.toContain(FAKE_KEY);
  });

  it("reports connection tests and saves the chat route with a fallback", async () => {
    const bridge = new FakeBridge();
    const { user } = mount(<ProviderSettings ready />, bridge);
    const card = article(await screen.findByRole("heading", { name: "Anthropic" }));
    await user.click(within(card).getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText(/Not reachable — Not configured/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Add fallback" }));
    await user.type(screen.getByLabelText("Model 2"), "gemma3");
    await user.click(screen.getByRole("button", { name: "Save route" }));
    await waitFor(() => {
      expect(bridge.routes.chat).toEqual([
        { provider_id: "ollama", model: "llama3.2" },
        { provider_id: "ollama", model: "gemma3" },
      ]);
    });
  });
});
