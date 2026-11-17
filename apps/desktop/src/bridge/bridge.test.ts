import { describe, expect, it, vi } from "vitest";

import { BackendError, createBridge, expectOk, type BackendBridge } from "./bridge";
import { listSettings, updateSetting } from "./api";

describe("createBridge", () => {
  it("calls exactly the three allowed commands with the expected arguments", async () => {
    const invoke = vi.fn((cmd: string) =>
      Promise.resolve(
        cmd === "backend_status" ? { state: "ready", detail: null } : { status: 200, body: {} },
      ),
    );
    const channel = { marker: "channel" };
    const bridge = createBridge(invoke, () => channel);

    await bridge.status();
    await bridge.request("PUT", "/v1/settings/a.b", { value: 1 });
    await bridge.request("GET", "/v1/health");
    await bridge.subscribe(() => undefined);

    expect(invoke.mock.calls).toEqual([
      ["backend_status"],
      ["backend_request", { method: "PUT", path: "/v1/settings/a.b", body: { value: 1 } }],
      ["backend_request", { method: "GET", path: "/v1/health", body: null }],
      ["subscribe_events", { onEvent: channel }],
    ]);
  });

  it("turns rejected bridge errors into BackendError with the bridge's code", async () => {
    const bridge = createBridge(
      // Tauri rejects with the serialized BridgeError object, not an Error instance.
      // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
      () => Promise.reject({ code: "route_not_allowed", message: "nope" }),
      () => ({}),
    );
    await expect(bridge.request("GET", "/v1/events")).rejects.toMatchObject({
      name: "BackendError",
      code: "route_not_allowed",
    });
  });
});

describe("expectOk", () => {
  it("returns the body for 2xx", () => {
    expect(expectOk({ status: 200, body: { a: 1 } })).toEqual({ a: 1 });
  });

  it("raises the backend's error code for non-2xx", () => {
    let caught: unknown;
    try {
      expectOk({ status: 422, body: { error: { code: "invalid_setting_value", message: "bad" } } });
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(BackendError);
    expect(caught).toMatchObject({ code: "invalid_setting_value", status: 422 });
  });

  it("raises a generic error when the body is not an error envelope", () => {
    expect(() => expectOk({ status: 500, body: "boom" })).toThrow(/500/);
  });
});

describe("settings api", () => {
  it("reads and writes settings through the bridge", async () => {
    const request = vi.fn((method: string) =>
      Promise.resolve(
        method === "GET"
          ? { status: 200, body: { settings: [{ key: "k", value: 1 }] } }
          : { status: 200, body: { key: "k", value: 2 } },
      ),
    );
    const bridge = { status: vi.fn(), subscribe: vi.fn(), request } as unknown as BackendBridge;
    expect(await listSettings(bridge)).toEqual([{ key: "k", value: 1 }]);
    expect(await updateSetting(bridge, "k", 2)).toEqual({ key: "k", value: 2 });
    expect(request).toHaveBeenLastCalledWith("PUT", "/v1/settings/k", { value: 2 });
  });
});
