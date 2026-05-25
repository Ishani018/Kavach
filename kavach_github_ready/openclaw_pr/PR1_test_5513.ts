/**
 * test/plugins/hook-runner-lazy.test.ts
 *
 * Regression test for OpenClaw issue #5513 — typed hooks registered after
 * initializeGlobalHookRunner() fail to fire because the runner snapshots
 * registry.typedHooks at construction time.
 *
 * Before fix: this test fails — `called` stays false.
 * After fix:  this test passes — handler fires on dispatch.
 *
 * Drop into: openclaw/test/plugins/hook-runner-lazy.test.ts
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { PluginRegistry } from "../../src/plugins/plugin-registry";
import {
  initializeGlobalHookRunner,
  getGlobalHookRunner,
  resetGlobalHookRunner,
} from "../../src/plugins/initialize-runner";
import type { BeforeToolCallEvent } from "../../src/plugins/hook-types";

function fakeEvent(): BeforeToolCallEvent {
  return {
    sessionKey: "s1",
    sessionId: "s1",
    turnNumber: 0,
    agentId: "agent-1",
    workspaceDir: "/tmp",
    modelId: "test-model",
    channel: "test",
    ts: Date.now(),
    correlationId: "corr-1",
    tool: { name: "exec", kind: "native" },
    toolCallId: "tc-1",
    args: { cmd: "ls" },
  };
}

describe("typed hook runner — late registration (#5513)", () => {
  let registry: PluginRegistry;

  beforeEach(() => {
    resetGlobalHookRunner();
    registry = new PluginRegistry();
    initializeGlobalHookRunner(registry);
  });

  it("dispatches to handlers registered AFTER initializeGlobalHookRunner", async () => {
    let called = false;

    // Late registration — this is what plugins do during their register() phase
    // which happens after initializeGlobalHookRunner runs at agent boot.
    registry.registerTypedHook("before_tool_call", async () => {
      called = true;
      return {};
    });

    await getGlobalHookRunner().dispatch("before_tool_call", fakeEvent());

    expect(called).toBe(true);
  });

  it("dispatches to multiple late-registered handlers in order", async () => {
    const order: string[] = [];

    registry.registerTypedHook("before_tool_call", async () => {
      order.push("a");
      return {};
    });
    registry.registerTypedHook("before_tool_call", async () => {
      order.push("b");
      return {};
    });
    registry.registerTypedHook("before_tool_call", async () => {
      order.push("c");
      return {};
    });

    await getGlobalHookRunner().dispatch("before_tool_call", fakeEvent());

    expect(order).toEqual(["a", "b", "c"]);
  });

  it("respects deny-first short-circuit on the runner", async () => {
    const calls: string[] = [];

    registry.registerTypedHook("before_tool_call", async () => {
      calls.push("first");
      return { block: true, blockReason: "test deny" };
    });
    registry.registerTypedHook("before_tool_call", async () => {
      calls.push("second");
      return {};
    });

    const result = await getGlobalHookRunner().dispatch(
      "before_tool_call",
      fakeEvent(),
    );

    expect(calls).toEqual(["first"]);
    expect(result.block).toBe(true);
    expect(result.blockReason).toBe("test deny");
  });

  it("merges params mutations across handlers (last writer wins)", async () => {
    registry.registerTypedHook("before_tool_call", async () => ({
      params: { cmd: "ls" },
    }));
    registry.registerTypedHook("before_tool_call", async () => ({
      params: { cmd: "ls -la" },
    }));

    const result = await getGlobalHookRunner().dispatch(
      "before_tool_call",
      fakeEvent(),
    );

    expect(result.params).toEqual({ cmd: "ls -la" });
  });

  it("survives a handler throwing — other handlers still fire", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    let secondCalled = false;

    registry.registerTypedHook("before_tool_call", async () => {
      throw new Error("boom");
    });
    registry.registerTypedHook("before_tool_call", async () => {
      secondCalled = true;
      return {};
    });

    await getGlobalHookRunner().dispatch("before_tool_call", fakeEvent());

    expect(secondCalled).toBe(true);
    errorSpy.mockRestore();
  });
});
