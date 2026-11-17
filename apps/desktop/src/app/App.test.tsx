import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FakeBridge } from "../test/fakeBridge";
import { SCREENS } from "../screens/registry";
import { App } from "./App";
import { BridgeProvider } from "./BridgeContext";

function renderApp(bridge = new FakeBridge()) {
  render(
    <BridgeProvider bridge={bridge}>
      <App />
    </BridgeProvider>,
  );
  return bridge;
}

describe("App shell", () => {
  it("lists all seven product screens plus preferences", () => {
    renderApp();
    const nav = screen.getByRole("navigation", { name: "Screens" });
    for (const s of SCREENS) {
      expect(within(nav).getByRole("button", { name: s.title })).toBeTruthy();
    }
  });

  it("shows an explicit 'Not available yet' state on unbuilt screens", async () => {
    renderApp();
    const user = userEvent.setup();
    const unbuilt = ["memory", "skills"];
    for (const s of SCREENS.filter((x) => unbuilt.includes(x.id))) {
      await user.click(screen.getByRole("button", { name: s.title }));
      expect(screen.getByRole("heading", { level: 1, name: s.title })).toBeTruthy();
      expect(screen.getByRole("heading", { name: "Not available yet" })).toBeTruthy();
      for (const part of s.planned) expect(screen.getByText(part.name)).toBeTruthy();
    }
  });

  it("shows backend status and version once the core is ready", async () => {
    renderApp();
    expect(await screen.findByText("Core connected")).toBeTruthy();
    expect(await screen.findByText(/core 0\.1\.0\.dev0/)).toBeTruthy();
  });

  it("shows the failure reason when the core fails to start", async () => {
    const bridge = new FakeBridge();
    bridge.statusView = { state: "failed", detail: "backend executable not found" };
    renderApp(bridge);
    expect(await screen.findByText("Core failed to start")).toBeTruthy();
    expect(screen.getByText("backend executable not found")).toBeTruthy();
  });
});

describe("Preferences round trip", () => {
  it("saves a setting through the bridge and applies reduced motion", async () => {
    const bridge = renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Preferences" }));
    const select = await screen.findByLabelText("Motion");
    await user.selectOptions(select, "on");

    await waitFor(() => {
      expect(document.documentElement.dataset.reducedMotion).toBe("on");
    });
    expect(bridge.calls).toContainEqual({
      method: "PUT",
      path: "/v1/settings/appearance.reduced_motion",
      body: { value: "on" },
    });
  });

  it("hides the status bar when the setting is turned off", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Preferences" }));
    expect(await screen.findByRole("status")).toBeTruthy();
    await user.click(await screen.findByLabelText("Show status bar"));
    await waitFor(() => {
      expect(screen.queryByRole("status")).toBeNull();
    });
  });

  it("shows the backend's error instead of pretending the save worked", async () => {
    const bridge = renderApp();
    bridge.failNextPut = { status: 422, code: "invalid_setting_value", message: "rejected value" };
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Preferences" }));
    await user.selectOptions(await screen.findByLabelText("Motion"), "off");
    expect((await screen.findByRole("alert")).textContent).toContain("rejected value");
    expect(screen.getByLabelText<HTMLSelectElement>("Motion").value).toBe("system");
  });

  it("applies setting changes pushed from the backend event stream", async () => {
    const bridge = renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Preferences" }));
    await screen.findByLabelText("Motion");
    await waitFor(() => {
      bridge.emit({
        type: "settings.changed",
        payload: { key: "appearance.reduced_motion", value: "off" },
      });
      expect(screen.getByLabelText<HTMLSelectElement>("Motion").value).toBe("off");
    });
  });
});
