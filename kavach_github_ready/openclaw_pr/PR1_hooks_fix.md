# PR-1: Fix OpenClaw bugs #5513 and #5943 — make `before_tool_call` actually fire

**Target repo:** `github.com/openclaw/openclaw`
**Branch:** `kavach/fix-typed-hook-runner-and-before-tool-call`
**Author:** Parv (PES University, capstone team)
**Reviewer (Kavach side):** Ishani
**Status:** Draft

---

## 1 · Why this PR exists

The OpenClaw plugin SDK exposes typed hooks (`before_tool_call`, `message_sending`, `agent_end`, etc.) but two bugs make them silently no-op in production:

- **#5513** — `initializeGlobalHookRunner()` snapshots `registry.typedHooks` *before* plugins finish registering during the brief `register()` → `start()` window. Hooks registered during that window are visible in the registry but invisible to the runner.
- **#5943** — Even if the runner saw the hook, `executeToolCalls()` in
  `src/agents/pi-embedded-runner/run/attempt.ts` (around line 254) never
  *calls* `before_tool_call`. The hook is defined in `src/plugins/hooks.ts`
  but no code path invokes it for tool execution in the general case.

  **Status note (May 2026):** GitHub UI shows #5943 as "Closed" with label
  `enhancement`. However, no v2026.5.x changelog entry references a commit
  wiring `before_tool_call` into the *general* `executeToolCalls()` path.
  The related entry "Auto-reply: gate inline skill tool dispatch through
  before-tool-call authorization hooks (#78517)" patches only the auto-reply
  skill dispatch path. The paper must say "closed without a corresponding
  wiring commit in the general v2026.5.x path" rather than "open bug" —
  a reviewer checking GitHub will see the Closed status and flag any
  inconsistency.

Until both are fixed, no security plugin (Kavach included) can actually intercept tool calls. The hooks register, then sit there.

The observability plugin's PR #6 (ISI-515) already worked around #5513 with a "lazy telemetry getter". We adopt that pattern as the canonical fix.

This PR is intentionally **small, additive, and back-compat**. It introduces no new public API surface. It does not change any payload schema. It is the smallest possible diff that makes the existing typed hooks fire.

---

## 2 · Files touched

```
src/plugins/hook-runner.ts         ← lazy getter for typedHooks (#5513 fix)
src/plugins/initialize-runner.ts    ← drop the eager snapshot (#5513 fix)
src/agents/pi-embedded-runner/run/attempt.ts   ← wire before_tool_call (#5943 fix)
test/plugins/hook-runner-lazy.test.ts          ← regression for #5513
test/agents/before-tool-call-fires.test.ts     ← regression for #5943
docs/automation/hooks.md           ← one-line correction (no functional change)
```

No schema changes. No new exports. No deprecations.

---

## 3 · The patches

### 3.1 Fix #5513 — lazy registry access in the hook runner

**File:** `src/plugins/hook-runner.ts`

The current runner caches a snapshot of `registry.typedHooks` at construction time. Replace the cached field with a getter that reads the live registry on every dispatch.

```ts
// BEFORE
export class TypedHookRunner {
  private hooks: TypedHookRegistry;

  constructor(registry: PluginRegistry) {
    this.hooks = registry.typedHooks;        // ← snapshot taken too early
  }

  async dispatch<E extends HookEvent>(event: E, payload: HookPayload<E>) {
    const handlers = this.hooks[event] ?? [];
    // ...
  }
}

// AFTER
export class TypedHookRunner {
  constructor(private readonly registry: PluginRegistry) {}

  private get hooks(): TypedHookRegistry {
    return this.registry.typedHooks;          // ← live read
  }

  async dispatch<E extends HookEvent>(event: E, payload: HookPayload<E>) {
    const handlers = this.hooks[event] ?? [];
    // ...
  }
}
```

This matches the pattern adopted by observability-plugin PR #6. No external behavior change for plugins that registered before `start()`; plugins that register late now work as documented.

**File:** `src/plugins/initialize-runner.ts`

Remove the eager snapshot. The runner is constructed with the registry reference and reads it on demand.

```ts
// BEFORE
export function initializeGlobalHookRunner(registry: PluginRegistry) {
  const snapshot = { ...registry.typedHooks };
  globalHookRunner = new TypedHookRunner(snapshot);
}

// AFTER
export function initializeGlobalHookRunner(registry: PluginRegistry) {
  globalHookRunner = new TypedHookRunner(registry);
}
```

### 3.2 Fix #5943 — actually invoke `before_tool_call` during tool execution

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`

In `executeToolCalls()`, before each tool runs, invoke the typed `before_tool_call` hook and respect its return value (`block`, `params`, `requireApproval`).

```ts
// BEFORE  (around line 254)
async function executeToolCalls(toolCalls: ToolCall[], ctx: RunContext) {
  const results: ToolResult[] = [];
  for (const call of toolCalls) {
    const tool = ctx.toolRegistry.get(call.name);
    if (!tool) {
      results.push({ id: call.id, error: `unknown tool: ${call.name}` });
      continue;
    }
    const result = await tool.execute(call.args, ctx);   // ← no hook invoked
    results.push({ id: call.id, result });
  }
  return results;
}

// AFTER
async function executeToolCalls(toolCalls: ToolCall[], ctx: RunContext) {
  const results: ToolResult[] = [];
  const runner = getGlobalHookRunner();

  for (const call of toolCalls) {
    const tool = ctx.toolRegistry.get(call.name);
    if (!tool) {
      results.push({ id: call.id, error: `unknown tool: ${call.name}` });
      continue;
    }

    // ─── #5943 fix: invoke before_tool_call ─────────────────────────────
    const hookResult = await runner.dispatch("before_tool_call", {
      sessionKey:    ctx.sessionKey,
      sessionId:     ctx.sessionId,
      turnNumber:    ctx.turnNumber,
      agentId:       ctx.agentId,
      workspaceDir:  ctx.workspaceDir,
      modelId:       ctx.modelId,
      ts:            Date.now(),
      correlationId: crypto.randomUUID(),
      tool: {
        name:     call.name,
        kind:     tool.kind,
        pluginId: tool.pluginId,
      },
      toolCallId: call.id,
      args:       call.args,
      rawArgs:    call.rawArgs,
    });

    if (hookResult?.block) {
      results.push({
        id:      call.id,
        error:   hookResult.blockReason ?? "blocked by typed hook",
        blocked: true,
      });
      continue;
    }
    if (hookResult?.requireApproval) {
      const approved = await ctx.userApproval(call, hookResult.requireApproval);
      if (!approved) {
        results.push({ id: call.id, error: "user denied approval", blocked: true });
        continue;
      }
    }
    const finalArgs = hookResult?.params ?? call.args;
    // ─── end fix ────────────────────────────────────────────────────────

    const result = await tool.execute(finalArgs, ctx);
    results.push({ id: call.id, result });
  }
  return results;
}
```

Sequential dispatch. Deny-first: any handler returning `block: true` short-circuits the call. `requireApproval` integrates with the existing approval flow added in v2026.3.28. `params` mutation is honored for handlers that want to redact or rewrite arguments (used by Kavach for argument sanitization later).

### 3.3 Documentation correction

**File:** `docs/automation/hooks.md`

The current `before_tool_call` section says "fires before tool execution". That is aspirational — until this PR, it doesn't fire at all. After this PR, the doc becomes accurate without any text change. The only edit is to remove the stale "Future Events" caveat next to `before_tool_call` (it lists the hook as available since v2026.3.28 but the wiring was never landed).

---

## 4 · Test plan

Two regression tests, one per bug. Both are <40 lines of vitest.

### 4.1 `test/plugins/hook-runner-lazy.test.ts` — regression for #5513

Verifies that a plugin which registers a hook *after* `initializeGlobalHookRunner()` still has its hook fire on dispatch.

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { PluginRegistry } from "../../src/plugins/plugin-registry";
import { initializeGlobalHookRunner, getGlobalHookRunner } from "../../src/plugins/initialize-runner";

describe("typed hook runner — late registration (#5513)", () => {
  let registry: PluginRegistry;

  beforeEach(() => {
    registry = new PluginRegistry();
    initializeGlobalHookRunner(registry);
  });

  it("dispatches to handlers registered after initializeGlobalHookRunner", async () => {
    let called = false;
    registry.registerTypedHook("before_tool_call", async () => {
      called = true;
      return {};
    });

    await getGlobalHookRunner().dispatch("before_tool_call", {
      sessionKey: "s1", sessionId: "s1", turnNumber: 0,
      agentId: "a", workspaceDir: "/tmp", modelId: "m",
      ts: Date.now(), correlationId: "c1",
      tool: { name: "exec", kind: "native" },
      toolCallId: "t1", args: { cmd: "ls" },
    });

    expect(called).toBe(true);
  });

  it("dispatches to multiple handlers in registration order", async () => {
    const order: string[] = [];
    registry.registerTypedHook("before_tool_call", async () => { order.push("a"); return {}; });
    registry.registerTypedHook("before_tool_call", async () => { order.push("b"); return {}; });

    await getGlobalHookRunner().dispatch("before_tool_call", { /* ... */ } as any);
    expect(order).toEqual(["a", "b"]);
  });
});
```

### 4.2 `test/agents/before-tool-call-fires.test.ts` — regression for #5943

Verifies that a synthetic tool call routed through `executeToolCalls()` triggers a registered `before_tool_call` handler, and that returning `block: true` prevents tool execution.

```ts
import { describe, it, expect, vi } from "vitest";
import { executeToolCalls } from "../../src/agents/pi-embedded-runner/run/attempt";
import { PluginRegistry } from "../../src/plugins/plugin-registry";
import { initializeGlobalHookRunner } from "../../src/plugins/initialize-runner";

describe("executeToolCalls invokes before_tool_call (#5943)", () => {
  it("fires before_tool_call before the tool runs", async () => {
    const registry = new PluginRegistry();
    initializeGlobalHookRunner(registry);

    const events: string[] = [];
    registry.registerTypedHook("before_tool_call", async (e) => {
      events.push(`hook:${e.tool.name}`);
      return {};
    });

    const tool = {
      name: "exec",
      kind: "native" as const,
      execute: vi.fn(async (args) => {
        events.push(`tool:${args.cmd}`);
        return "ok";
      }),
    };
    const ctx = makeFakeRunContext({ tools: [tool] });

    await executeToolCalls([{ id: "t1", name: "exec", args: { cmd: "ls" } }], ctx);

    expect(events).toEqual(["hook:exec", "tool:ls"]);
    expect(tool.execute).toHaveBeenCalledOnce();
  });

  it("respects block:true and does not run the tool", async () => {
    const registry = new PluginRegistry();
    initializeGlobalHookRunner(registry);

    registry.registerTypedHook("before_tool_call", async () => ({
      block: true, blockReason: "denied by Kavach minister EXECUTOR",
    }));

    const tool = {
      name: "exec", kind: "native" as const,
      execute: vi.fn(),
    };
    const ctx = makeFakeRunContext({ tools: [tool] });

    const results = await executeToolCalls(
      [{ id: "t1", name: "exec", args: { cmd: "rm -rf /" } }], ctx,
    );

    expect(tool.execute).not.toHaveBeenCalled();
    expect(results[0]).toMatchObject({
      id: "t1", blocked: true,
      error: "denied by Kavach minister EXECUTOR",
    });
  });

  it("respects params mutation for argument redaction", async () => {
    const registry = new PluginRegistry();
    initializeGlobalHookRunner(registry);

    registry.registerTypedHook("before_tool_call", async () => ({
      params: { cmd: "ls -la" }, // hook redacts dangerous flag
    }));

    const tool = {
      name: "exec", kind: "native" as const,
      execute: vi.fn(async (args) => args.cmd),
    };
    const ctx = makeFakeRunContext({ tools: [tool] });

    await executeToolCalls(
      [{ id: "t1", name: "exec", args: { cmd: "ls -la --dangerous" } }], ctx,
    );

    expect(tool.execute).toHaveBeenCalledWith({ cmd: "ls -la" }, ctx);
  });
});

function makeFakeRunContext({ tools }: { tools: any[] }) {
  return {
    sessionKey: "s1", sessionId: "s1", turnNumber: 0,
    agentId: "a", workspaceDir: "/tmp", modelId: "m",
    toolRegistry: { get: (n: string) => tools.find((t) => t.name === n) },
    userApproval: async () => true,
  } as any;
}
```

---

## 5 · Why we are confident maintainers will merge

Looking at the recent v2026.5.x release notes and the maintainer review patterns, this PR matches every acceptance signal:

- **Small and additive.** ~80 lines of source change, ~120 lines of test.
- **Bug fix, not a feature.** The hooks are documented as available since v2026.3.28; this PR makes the documentation true.
- **Existing precedent.** observability-plugin PR #6 (ISI-515) shipped the lazy-getter pattern; we are generalizing it to the global hook runner.
- **Vitest coverage.** Both bugs have regression tests; future refactors cannot reintroduce them silently.
- **No schema break.** No `TypeBox` schema changes. No payload field additions. Public API unchanged.
- **Backwards compatible.** Plugins that worked before (registered eagerly) still work. Plugins that were silently broken (registered late) now work.
- **Discussion #9872 alignment.** Comment on Discussion #9872 announcing the workstream so the ClawRouter team and maintainers see context.

Submission order:

1. Reproduce both bugs locally on `v2026.5.x`. Capture failing test runs as the issue evidence.
2. Open the PR with the two regression tests as the first commit; the fixes as the second commit. This makes the diff narrative obvious: "tests fail before fix, pass after."
3. Link the PR to issues #5513 and #5943. CC `@steipete`-era reviewers (now under the foundation maintainer rotation).
4. Comment on Discussion #9872 with one line: "PR-1 ships the prerequisite for the structured-verdict work coming in PR-2/PR-3."

If the PR stalls beyond 14 days, ship the fix as a monkey-patch inside the npm `@pesu/openclaw-plugin-kavach` package (Section 5.1 of the OpenClaw integration reference doc) so Kavach is unblocked regardless.

---

## 6 · After this PR lands

- **PR-2** — internal-hook discoverability for `before_tool_call` and `message_sending` (HOOK.md path support, ~150 lines).
- **PR-3** — structured-verdict payload extension (TypeBox additions for `verdict_code`, `kavach_correlation_id`, `redaction_patch`).
- **Plugin** — ship `@pesu/openclaw-plugin-kavach` to npm, registering on `before_tool_call` and calling the parliament HTTP endpoint at `127.0.0.1:8088/hook/parliament`.

This PR alone unblocks all of the above. None of it works without it.
