import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { BridgeProvider } from "../app/BridgeContext";
import { FakeBridge } from "../test/fakeBridge";
import { approval, auditEntry, grant, receipt, task } from "../test/fakeTrust";
import { ActivityCenter } from "./ActivityCenter";
import { SecurityCenter } from "./SecurityCenter";
import { TaskHistory } from "./TaskHistory";

function article(el: HTMLElement): HTMLElement {
  const found = el.closest("article");
  if (!found) throw new Error("not inside an article");
  return found;
}

function mount(ui: React.ReactElement, bridge: FakeBridge) {
  render(<BridgeProvider bridge={bridge}>{ui}</BridgeProvider>);
  return userEvent.setup();
}

describe("Activity Center", () => {
  it("shows what, why, service, data and consequences, and approves via the backend", async () => {
    const bridge = new FakeBridge();
    bridge.approvals = [approval()];
    const user = mount(<ActivityCenter ready />, bridge);
    const card = article(await screen.findByText("Record a fixture effect"));
    for (const text of [
      "Acceptance test",
      "Local fixture server",
      "One record",
      "A counter increases",
    ]) {
      expect(within(card).getByText(text)).toBeTruthy();
    }
    await user.click(within(card).getByRole("button", { name: "Approve" }));
    expect(bridge.calls).toContainEqual({
      method: "POST",
      path: "/v1/approvals/01JAPPROVAL000000000000000/decision",
      body: { approve: true },
    });
    expect(await screen.findByText("Nothing is waiting for your approval.")).toBeTruthy();
  });

  it("routes highest-risk approvals through the native dialog only", async () => {
    const bridge = new FakeBridge();
    bridge.approvals = [approval({ highest_risk: true, category: "send_message" })];
    bridge.nativeDialogApproves = false;
    const user = mount(<ActivityCenter ready />, bridge);
    const button = await screen.findByRole("button", { name: "Review in macOS dialog…" });
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    await user.click(button);
    expect((await screen.findByRole("alert")).textContent).toContain("still pending");
    expect(bridge.approvals).toHaveLength(1); // cancelling the dialog decides nothing
    bridge.nativeDialogApproves = true;
    await user.click(screen.getByRole("button", { name: "Review in macOS dialog…" }));
    expect(await screen.findByText("Nothing is waiting for your approval.")).toBeTruthy();
    expect(bridge.calls.some((c) => c.path.endsWith("/decision"))).toBe(false);
  });

  it("offers the three Needs-review choices and labels attestation honestly", async () => {
    const bridge = new FakeBridge();
    bridge.tasks = [{ task: task(), receipt: receipt() }];
    const user = mount(<ActivityCenter ready />, bridge);
    expect(await screen.findByText("Uncertain — outcome unknown")).toBeTruthy();
    expect(screen.getByText(/recorded as user-attested, not verified/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel task" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "It happened" }));
    expect(bridge.calls).toContainEqual({
      method: "POST",
      path: "/v1/tasks/T1/review",
      body: { action_id: "A1", choice: "happened" },
    });
  });
});

describe("Security Center", () => {
  it("shows chain status, filters events and exports through the native dialog", async () => {
    const bridge = new FakeBridge();
    bridge.audit = [auditEntry(2, "approval.approved"), auditEntry(1, "task.created")];
    const user = mount(<SecurityCenter ready />, bridge);
    expect(await screen.findByText(/Chain intact · 2 entries verified/)).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("Event type"), "approval.");
    await waitFor(() => {
      expect(screen.queryByText("task.created")).toBeNull();
    });
    expect(screen.getByText("approval.approved")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(await screen.findByText("Saved to /Users/me/jarvis-audit.csv")).toBeTruthy();
  });

  it("reports a broken chain instead of hiding it", async () => {
    const bridge = new FakeBridge();
    bridge.chainOk = false;
    mount(<SecurityCenter ready />, bridge);
    expect(await screen.findByText(/Chain broken at entry 2/)).toBeTruthy();
  });

  it("grants and revokes directory access, refusing relative paths", async () => {
    const bridge = new FakeBridge();
    bridge.grants = [grant()];
    const user = mount(<SecurityCenter ready />, bridge);
    expect(await screen.findByText("/Users/me/Documents")).toBeTruthy();
    const input = screen.getByLabelText("Folder to grant");
    await user.type(input, "Documents");
    await user.click(screen.getByRole("button", { name: "Grant access" }));
    expect((await screen.findByRole("alert")).textContent).toContain("absolute folder path");
    await user.clear(input);
    await user.type(input, "/Users/me/Projects");
    await user.click(screen.getByRole("button", { name: "Grant access" }));
    expect(await screen.findByText("/Users/me/Projects")).toBeTruthy();
    const [firstRevoke] = screen.getAllByRole("button", { name: "Revoke" });
    if (!firstRevoke) throw new Error("no revoke button");
    await user.click(firstRevoke);
    await waitFor(() => {
      expect(screen.queryByText("/Users/me/Documents")).toBeNull();
    });
  });
});

describe("Task History", () => {
  it("shows a task's receipt with honest status labels", async () => {
    const bridge = new FakeBridge();
    bridge.tasks = [{ task: task(), receipt: receipt() }];
    const user = mount(<TaskHistory ready />, bridge);
    await user.click(await screen.findByRole("button", { name: /Send the invoice/ }));
    expect(await screen.findByText("Uncertain — outcome unknown")).toBeTruthy();
    expect(screen.getByText(/the outcome of an action is unknown/)).toBeTruthy();
  });
});
