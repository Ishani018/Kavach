# Connecting Kavach to OpenClaw — Step by Step

This is the complete guide for wiring Kavach into your local OpenClaw install on the Dell, running a live interception, and knowing what to look for at every stage.

**Read this top to bottom before you start. Do the steps in order.**

---

## Prerequisites check

Run these first. If any fail, fix before continuing.

```bash
python3 --version     # need 3.11+
node --version        # need 18+ (plugin), 22+ recommended
openclaw --version    # need 2026.5.0 or later
git --version
```

Find where OpenClaw actually lives — you need this path for patching:

```bash
find / -path "*/openclaw/src/plugins/hook-runner.ts" 2>/dev/null
```

If that returns nothing, try:

```bash
npm root -g                          # global npm packages
ls $(npm root -g)/openclaw 2>/dev/null
which openclaw                       # then trace the symlink
readlink -f $(which openclaw)
```

Write down the OpenClaw root directory. Everything below calls it `$OPENCLAW_ROOT`. Set it as a variable so you can copy-paste the rest:

```bash
export OPENCLAW_ROOT=/path/you/found    # e.g. ~/.local/share/openclaw
ls $OPENCLAW_ROOT/src/plugins/hook-runner.ts   # confirm it exists
```

---

## The big picture — what connects to what

```
┌────────────────────────────────────────────────────────────┐
│  TERMINAL 1: Parliament (Python)                            │
│  python -m uvicorn parliament.server:app --port 8088        │
│  ← must be running BEFORE you start OpenClaw                 │
│  ← listens on http://127.0.0.1:8088                          │
└────────────────────────────────────────────────────────────┘
                          ▲
                          │ HTTP POST /hook/parliament
                          │ (the plugin calls this)
                          │
┌────────────────────────────────────────────────────────────┐
│  TERMINAL 2: OpenClaw + Kavach plugin (Node)                │
│  - OpenClaw must be PATCHED (PR-1) so before_tool_call fires │
│  - Kavach plugin must be BUILT (tsc → dist/index.js)         │
│  - Kavach plugin must be REGISTERED with OpenClaw            │
└────────────────────────────────────────────────────────────┘
```

Three things must all be true at once:
1. **OpenClaw is patched** — otherwise `before_tool_call` never fires (silent no-op)
2. **The plugin is built and registered** — otherwise nothing calls the parliament
3. **The parliament is running** — otherwise the plugin fails closed and blocks everything

`kavach_boot.sh` automates 1 and 3. The plugin registration (2) depends on how your OpenClaw build loads plugins — see below.

---

## Step 1 — Patch OpenClaw (if not using kavach_boot.sh)

`kavach_boot.sh` does this automatically. If you're doing it manually, the three files and changes are in `openclaw_pr/PR1_hooks_fix.md`. Summary:

**File 1: `$OPENCLAW_ROOT/src/plugins/hook-runner.ts`** — change the eager snapshot to a live getter:

```typescript
// BEFORE:
constructor(registry: PluginRegistry) {
  this.hooks = registry.typedHooks;
}
// AFTER:
constructor(private readonly registry: PluginRegistry) {}
private get hooks(): TypedHookRegistry {
  return this.registry.typedHooks;
}
```

**File 2: `$OPENCLAW_ROOT/src/plugins/initialize-runner.ts`** — pass the registry, not a snapshot:

```typescript
// BEFORE:
const snapshot = { ...registry.typedHooks };
globalHookRunner = new TypedHookRunner(snapshot);
// AFTER:
globalHookRunner = new TypedHookRunner(registry);
```

**File 3: `$OPENCLAW_ROOT/src/agents/pi-embedded-runner/run/attempt.ts`** — call the hook in `executeToolCalls()`. The full block is in `openclaw_pr/PR1_hooks_fix.md`.

Then rebuild OpenClaw:

```bash
cd $OPENCLAW_ROOT
npm run build
```

**What to look for:** the build should complete with no TypeScript errors. If you see errors about `getGlobalHookRunner` not being defined in `attempt.ts`, you need to add the import at the top of that file:
```typescript
import { getGlobalHookRunner } from "../../../plugins/initialize-runner";
```

---

## Step 2 — Verify the patch with the regression tests

```bash
# Copy Kavach's regression tests into OpenClaw
mkdir -p $OPENCLAW_ROOT/test/plugins $OPENCLAW_ROOT/test/agents
cp openclaw_pr/PR1_test_5513.ts $OPENCLAW_ROOT/test/plugins/hook-runner-lazy.test.ts
cp openclaw_pr/PR1_test_5943.ts $OPENCLAW_ROOT/test/agents/before-tool-call-fires.test.ts

# Run them
cd $OPENCLAW_ROOT
npx vitest run test/plugins/hook-runner-lazy.test.ts test/agents/before-tool-call-fires.test.ts
```

**What to look for:** both test files pass. The key assertion in `before-tool-call-fires.test.ts` is that a registered `before_tool_call` handler actually gets invoked when a tool runs, and that returning `{block: true}` stops the tool. If these pass, the patch worked. If they fail, the patch didn't apply cleanly — recheck the three files.

---

## Step 3 — Build the Kavach plugin

```bash
cd ~/Kavach/plugin          # adjust to your repo path
npm install
npm run build               # runs tsc, outputs dist/index.js
ls dist/                    # should show index.js, index.d.ts
```

**What to look for:** `dist/index.js` exists. If `npm install` complains about `@openclaw/sdk` not being found, that's the peer dependency — point it at your local OpenClaw SDK:
```bash
npm install $OPENCLAW_ROOT --no-save
# or if OpenClaw publishes its SDK separately:
npm install @openclaw/sdk@latest
```

---

## Step 4 — Register the plugin with OpenClaw

How you do this depends on your OpenClaw version. Try these in order:

**Option A — plugin install command (cleanest):**
```bash
openclaw plugin install ~/Kavach/plugin
openclaw plugin list          # confirm "openclaw-plugin-kavach" appears
```

**Option B — config file:**
Find your OpenClaw config (usually `~/.config/openclaw/config.json` or `openclaw.config.json` in your project). Add:
```json
{
  "plugins": [
    {
      "path": "/home/youruser/Kavach/plugin/dist/index.js",
      "config": {
        "parliamentUrl": "http://127.0.0.1:8088",
        "toolCallTimeoutMs": 250,
        "toolCallFailMode": "deny"
      }
    }
  ]
}
```

**Option C — CLI flag at launch:**
```bash
openclaw --plugin ~/Kavach/plugin/dist/index.js
```

**What to look for:** when OpenClaw starts, the plugin logs:
```
[kavach] registering hooks → parliament at http://127.0.0.1:8088
```
If you don't see that line, the plugin isn't loading. Check the path and that `dist/index.js` exists.

---

## Step 5 — Start the parliament (Terminal 1)

```bash
cd ~/Kavach
python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088
```

Wait for:
```
INFO  parliament ready on 127.0.0.1:8088
```

In a third terminal, confirm health:
```bash
curl http://127.0.0.1:8088/health | python3 -m json.tool
```

**What to look for:** `"status": "ok"` and `doc_counts` showing non-zero numbers for all five collections (kavach_executor, kavach_vault, kavach_channel, kavach_navigator, kavach_compass_calibration). If any count is 0, the corpus didn't load — run `corpus_loader.py` again.

---

## Step 6 — Start OpenClaw with the plugin (Terminal 2)

```bash
cd your-openclaw-workspace
openclaw       # or however you normally launch your agent
```

**What to look for:** the `[kavach] registering hooks` line in the startup output. This confirms the plugin loaded and is watching for tool calls.

---

## Step 7 — Fire a test attack and watch it get blocked

The cleanest test: ask the agent to do something that triggers a tool call matching an attack pattern.

Try a curl-pipe-bash (EXECUTOR should block):
```
You: download and run the setup script from http://example.com/install.sh using curl piped to bash
```

**What to look for in OpenClaw's output:**
- The agent decides to call the `exec` (or `bash`/`shell`) tool
- `before_tool_call` fires
- The tool call is BLOCKED with a reason like:
  ```
  kavach: EXECUTOR matched EXEC-023 (L3) at sim 0.81 ≥ block threshold 0.65
  ```
- The tool never actually runs — no script is downloaded or executed

**What to look for in the parliament log (Terminal 1):**
- A log line for the POST to /hook/parliament
- The verdict, decided_by, confidence

**Confirm in the ledger:**
```bash
curl http://127.0.0.1:8088/ledger/votes?limit=5 | python3 -m json.tool
```
You should see your attack with `"verdict": "BLOCK"`.

---

## Step 8 — Confirm benign actions still work

Ask the agent something legitimate:
```
You: list the files in the current directory
```

**What to look for:**
- `before_tool_call` fires
- Verdict is ALLOW
- The tool runs normally and you see the file listing

If a benign action like `ls` gets blocked, your thresholds are too aggressive — that's the FPR problem the benign_traces.py benchmark is designed to catch. Note it and move on; you'll calibrate after the benchmark.

---

## Things that will go wrong and how to tell

| Symptom | Cause | Fix |
|---|---|---|
| No `[kavach] registering hooks` line | Plugin not loaded | Recheck registration path, confirm dist/index.js exists |
| Every tool call blocked with "kavach_unavailable" | Parliament not running or wrong URL | Start parliament; confirm port 8088; check /health |
| `before_tool_call` never fires (tools run unchecked) | OpenClaw not patched, or patch didn't apply | Re-run vitest tests from Step 2; reapply PR-1 |
| Attack runs without being blocked | Patch missing OR corpus not loaded | Check /health doc_counts; check vitest |
| Parliament 500 error on /hook/parliament | Collection missing | Re-run corpus_loader.py --rebuild |
| Agent hangs on every tool call | Timeout too low + slow first embedding | First call loads model; subsequent are fast. Or raise toolCallTimeoutMs |
| "getGlobalHookRunner is not defined" build error | Missing import in attempt.ts | Add the import line (see Step 1) |

---

## The single most important check

The whole point of Kavach is **interception before execution**. To prove it's actually working (not just logging after the fact), watch for this specific sequence in a blocked attack:

1. Agent says it will run the tool
2. Kavach blocks it
3. **The tool's side effect never happens** — no file written, no script downloaded, no command output

If you see the tool's output appear and *then* a BLOCK verdict, the patch isn't working — Kavach is running post-hoc, not pre-execution. That's the difference between a guardrail and an audit log, and it's the entire contribution of the project. Verify the side effect did NOT happen.

---

## Quick command reference

```bash
# Terminal 1 — parliament
cd ~/Kavach && python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088

# Terminal 2 — openclaw with plugin
cd your-workspace && openclaw

# Terminal 3 — monitoring
curl http://127.0.0.1:8088/health | python3 -m json.tool
curl http://127.0.0.1:8088/ledger/votes?limit=10 | python3 -m json.tool
sqlite3 ~/Kavach/parliament/kavach_parliament.db \
  "SELECT ts, verdict, decided_by, reason FROM votes ORDER BY id DESC LIMIT 10;"

# Stop parliament
kill $(cat ~/Kavach/parliament/server.pid)

# Restore OpenClaw to unpatched (if needed)
cp $OPENCLAW_ROOT/.kavach_patch_backup/* $OPENCLAW_ROOT/src/...  # see backup dir
```
