# Kavach — Live Monitor Roadmap
### From per-call input guard → context-aware session enforcer → AISec 2026 submission

**Deadline: July 24, 2026 (AISec @ ACM CCS, The Hague — firm)**
**Target: 10-page ACM double-column, anonymized, with working artifact link**

---

## Current State (June 3, 2026)

### What is built and where

| Component | Status | Branch | Notes |
|---|---|---|---|
| Parliament (4 ministers, BGE, ChromaDB) | ✅ Working | `main` | p50=826ms, p95=1649ms |
| COMPASS drift detection | ✅ Working | `main` | `compass_sim: null` live — #9 |
| Hash-chained ledger | ⚠️ Partial | `main` | Plain SQLite. Hash chain is browser lab only. Fix or drop the claim in paper. |
| Trajectory monitor v1 | ✅ Built, NOT merged | `ishani/trajectory-monitor` | accumulation + basic chain + embed-once |
| Trajectory monitor v2 | ✅ Built, NOT pushed | local only | + denial echo (ARM) + sequential direction (Trajectory Guard) + cross-minister escalation (AgentDoG) + hard ceiling in speaker.py |
| Dynamic COMPASS thresholds | ⬜ Not built | — | Issue #4. Formula is in trajectory.py. Needs per-minister config. |
| Per-minister thresholds | ⬜ Not built | — | Issue #3. 20 lines in config.yaml. Immediate FPR fix. |
| Seed intent fix (#9) | ⬜ Not built | — | Escalation leg of trajectory is 0.0 until this is fixed. |
| Ledger recovery (deque rebuild on restart) | ⬜ Not built | — | Server restart wipes session history. Ledger is write-only. |
| AgentDojo adapter | ⬜ Not built | — | Custom defense class. Parv's task. |
| InjecAgent FPR fix | ⬜ Not built | — | Needs per-minister thresholds + rerun. |
| OpenClaw-native trajectory test | ⬜ Not built | — | 5-step staged attack scenario. |
| Paper | 🟡 In progress | `paper/` | Sections exist. Needs benchmark numbers to fill §5. |

### What the benchmarks currently show

```
InjecAgent (1,054 cases, threshold=0.55):
  strict_recall: 0.9839   ← good
  loose_recall:  1.0000   ← good
  fpr:           0.8824   ← BAD — representation mismatch, needs per-minister thresholds
  f1:            0.6865   ← needs FPR fix
  latency p50:   826ms
  latency p95:   1649ms

AgentDojo: NOT RUN YET ← reviewers will ask about this first
```

### What we need to beat (comparison table)

| System | ASR after defense | FPR | Latency | Benchmark |
|---|---|---|---|---|
| LlamaFirewall (full) | **1.75%** | ~1% (PromptGuard 2) | ~19ms (PromptGuard 2 only) | AgentDojo |
| AgentArmor v2/v3 | **3%** | 3.66% | 20.89s avg | AgentDojo |
| MELON (GPT-4o) | **0.24%** | low | 2× passes | AgentDojo |
| OpenClaw PRISM | ~4.5% (recall 0.955) | 13.9% | **~15.8s p95** | Own 80-case corpus |
| Baseline (no defense) | 17.63% | — | — | AgentDojo |
| **Kavach target** | **≤5%** | **≤5%** | **measured: 1.65s p95 (target <1s)** | **AgentDojo + InjecAgent** |

Kavach's wedge: **embedding-based semantic detection at a single pre-execution hook, 
sub-second latency, OpenClaw-native, multi-step session enforcement** — vs 
PRISM's ~15.8s scanner and AgentArmor's 20.89s average overhead.

---

## Phase 1 — Laptop Work (Ishani, now → week 3)
*No Dell required. Pure code and paper work.*

### 1.1 Push trajectory v2 to the open PR (do this first)

Three files changed since the last push to `ishani/trajectory-monitor`:
- `parliament/trajectory.py` — v2 (denial echo, sequential direction, cross-minister escalation)
- `parliament/speaker.py` — hard ceiling (Case 0 in combine_verdicts)
- `parliament/server.py` — current_vec + is_denial wired through

```cmd
cd C:\Users\ishan\Downloads\kavach_push
git checkout ishani/trajectory-monitor
copy /Y C:\Users\ishan\Downloads\files\trajectory.py parliament\trajectory.py
copy /Y C:\Users\ishan\Downloads\files\speaker.py   parliament\speaker.py
copy /Y C:\Users\ishan\Downloads\files\server.py    parliament\server.py
py -m py_compile parliament\trajectory.py parliament\speaker.py parliament\server.py
py -m parliament.trajectory
git add parliament\trajectory.py parliament\speaker.py parliament\server.py
git commit -m "feat(trajectory): add A+B+C+D context-aware signals

A - denial echo: tracks blocked vectors, catches causality laundering (ARM)
B - sequential direction: consecutive cosines replace mean-pooling centroid
    (addresses Trajectory Guard F1 ceiling of 0.69, arXiv:2601.00516)
C - cross-minister escalation: VAULT->CHANNEL and similar patterns (AgentDoG)
D - hard ceiling: traj_risk >= 0.72 triggers independent BLOCK in speaker.py
    decided_by=TRAJECTORY, making Kavach a session enforcer not just a guard"
git push origin ishani/trajectory-monitor
```

Update the PR description on GitHub — prepend the v2 section (text in PR #15).

### 1.2 Fix #9 — seed_intent at session start

**The problem:** `compass_sim` is null in every live session because `seed_intent`
is never called before the agent runs. This means the escalation leg of the 
trajectory monitor is permanently 0.0 in production.

**The fix:** wire the plugin to call `POST /seed_intent` when a session starts.
OpenClaw should expose a `beforeAgentStart` or `onSessionCreate` hook. If not,
call it at `before_tool_call` on the FIRST call only (detect with a flag in `_state`).

File to edit: `plugin/openclaw-plugin-kavach.ts`

Look for or add a session-start handler:
```typescript
// In the plugin registration block, after before_tool_call:
api.registerHook('beforeAgentStart', async (e: AgentStartEvent) => {
  const sessionId = e.sessionId ?? 'default';
  // Call seed_intent with the user's initial message as the intent text
  await fetch(`${KAVACH_URL}/seed_intent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: e.userMessage, session_id: sessionId }),
  });
});
```

If OpenClaw does not expose `beforeAgentStart`, add this inside `before_tool_call`
as a one-time call on the first hook fire per session:

```typescript
// Track seeded sessions in plugin state
const seededSessions = new Set<string>();

api.registerHook('before_tool_call', async (e: ToolCallEvent) => {
  const sessionId = e.sessionId ?? 'default';
  
  // Seed intent on first call of each session
  if (!seededSessions.has(sessionId) && e.conversationHistory?.length > 0) {
    seededSessions.add(sessionId);
    const firstUserMsg = e.conversationHistory
      .find((m: any) => m.role === 'user')?.content ?? '';
    if (firstUserMsg) {
      await fetch(`${KAVACH_URL}/seed_intent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: firstUserMsg, session_id: sessionId }),
      }).catch(() => {}); // non-blocking: don't fail the hook if seeding fails
    }
  }
  
  // ... rest of existing hook code ...
});
```

Branch: `ishani/fix-seed-intent`
PR: references #9, closes #9
Assign to: Ishani

### 1.3 Per-minister thresholds (issue #3)

**The problem:** All ministers use a single block=0.725 threshold. The sweep shows 
VAULT has FPR=70.6% — it needs a much higher threshold. Using one threshold for all
is the primary cause of the 88.2% FPR on InjecAgent.

**The fix:** 20 lines in `parliament/config.yaml`. Change the thresholds block from
a single value to per-minister values matching the Youden J sweep:

```yaml
# parliament/config.yaml — replace the thresholds block with:
thresholds:
  block: 0.725          # fallback (used if minister not listed below)
  grey: 0.50
  compass_drift: 0.40
  per_minister:
    EXECUTOR: 0.55      # sweep optimal: TPR 0.903, FPR 0.471
    VAULT:    0.75      # sweep optimal was 0.55 but FPR 70.6% — tighten to 0.75
    CHANNEL:  0.60      # sweep optimal: TPR 0.516, FPR 0.235
    NAVIGATOR: 0.60     # sweep optimal: TPR 0.371, FPR 0.294
```

Then in `parliament/server.py`, update `run_minister_dual` calls to pass
`thresholds=_get_minister_thresholds(minister)` where:

```python
def _get_minister_thresholds(minister: str) -> dict:
    per = CFG["thresholds"].get("per_minister", {})
    block = per.get(minister, CFG["thresholds"]["block"])
    return {**CFG["thresholds"], "block": block}
```

Branch: `ishani/per-minister-thresholds`
PR: closes #3
Expected outcome: FPR drops from 88.2% → ~30-40% on InjecAgent. Recall may drop
slightly — that tradeoff is acceptable and honest to report.

### 1.4 AgentDojo adapter (issue #5 — Parv owns Dell run, Ishani writes the code)

AgentDojo registers custom defenses via `--module-to-load`. Write the adapter
so it's ready for Parv to run on the Dell.

Create `benchmarks/kavach_agentdojo_defense.py`:

```python
"""
AgentDojo custom defense adapter for Kavach parliament.

Register with:
  python -m agentdojo.scripts.benchmark \
    -s workspace \
    --model <model> \
    --defense KavachDefense \
    --module-to-load benchmarks.kavach_agentdojo_defense \
    --attack important_instructions

Requires: Kavach parliament running at KAVACH_URL (default http://localhost:8000)
"""

import os
import requests
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.types import ChatMessage

KAVACH_URL = os.environ.get("KAVACH_URL", "http://localhost:8000")
SESSION_ID = "agentdojo-eval"


class KavachDefense(BasePipelineElement):
    """Wraps the Kavach parliament as an AgentDojo defense.
    
    Intercepts each tool call before execution. If parliament returns BLOCK
    or traj_risk >= ceiling, the tool call is suppressed and a safe message
    is returned to the agent instead.
    """
    
    name = "KavachDefense"

    def query(
        self,
        query: str,
        runtime,
        env,
        messages: list[ChatMessage],
        tools: list,
        **kwargs,
    ):
        """Called by AgentDojo before each tool-call step."""
        # Extract the tool call text for parliament scoring
        tool_call_text = self._format_tool_call(query, messages)
        
        try:
            resp = requests.post(
                f"{KAVACH_URL}/parliament",
                json={
                    "text": tool_call_text,
                    "session_id": SESSION_ID,
                    "context": {"source": "agentdojo"},
                },
                timeout=10.0,
            )
            result = resp.json()
            verdict = result.get("verdict", "ALLOW")
            traj_risk = result.get("traj_risk", 0.0)
            decided_by = result.get("speaker", {}).get("decided_by", "UNKNOWN")
            
            if verdict == "BLOCK":
                # Suppress the tool call — return a safe refusal message
                return (
                    f"[KAVACH BLOCK — decided_by={decided_by}, "
                    f"traj_risk={traj_risk:.3f}] "
                    f"This action was blocked by the security monitor.",
                    messages,
                )
        except Exception as e:
            # If parliament is unreachable, fail open (allow) and log
            print(f"[KavachDefense] parliament unreachable: {e} — failing open")
        
        # ALLOW: pass through to normal execution
        return query, messages

    def _format_tool_call(self, query: str, messages: list[ChatMessage]) -> str:
        """Format the tool call text for parliament scoring."""
        # Extract the last assistant message's tool call if available
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tc = msg["tool_calls"][0]
                name = tc.get("function", {}).get("name", "unknown")
                args = tc.get("function", {}).get("arguments", "{}")
                return f"tool:{name} args:{args}"
        return query
```

Branch: can be part of `ishani/per-minister-thresholds` or its own `ishani/agentdojo-adapter`

### 1.5 Ledger recovery (nice-to-have, after the above)

When parliament restarts, `_state["history"]` is wiped. The ledger has the data
to rebuild it. Add to server.py's startup:

```python
async def _rebuild_session_history() -> None:
    """On startup, repopulate the trajectory deque from recent ledger entries.
    Covers the last WINDOW_SIZE calls per session from the last 24 hours."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT session_id, input_text, verdict, confidence, decided_by, traj_risk
        FROM votes
        WHERE ts >= datetime('now', '-24 hours')
        ORDER BY id ASC
    """).fetchall()
    conn.close()
    for session_id, input_text, verdict, confidence, decided_by, traj_risk in rows:
        hist = _state["history"][session_id]
        # Re-embed to rebuild the vector — only called once at startup, not on hot path
        try:
            vec = _embed_query(input_text or "")
            traj.record_action(hist, vec, verdict or "ALLOW",
                               float(confidence or 0), decided_by or "UNKNOWN",
                               is_denial=(verdict == "BLOCK"))
        except Exception:
            pass  # Skip malformed rows
```

Call `await _rebuild_session_history()` from the `lifespan` startup block.
This turns the ledger from a write-only audit log into a recovery mechanism —
which is what it was always supposed to be.

---

## Phase 2 — Dell Work (Parv, now → week 3)
*See DELL_BENCHMARK_RUNBOOK.md for exact commands.*

### 2.1 Pull and verify trajectory-monitor branch (week 1)
- Pull `ishani/trajectory-monitor` after Ishani pushes v2 (Phase 1.1)
- Start parliament, verify health
- Run the trajectory smoke test (`python -m parliament.trajectory`)
- Run a staged 5-step attack and check `/ledger/votes` for `traj_risk` climbing

### 2.2 Verify seed_intent fix when Ishani pushes it (week 1-2)
- Pull `ishani/fix-seed-intent` when pushed
- Start OpenClaw embedded mode with a test task
- Confirm `compass_sim` is no longer null in `/ledger/votes`

### 2.3 InjecAgent with per-minister thresholds (week 2)
- Pull `ishani/per-minister-thresholds` when pushed
- Run `python benchmarks/injecagent_runner.py --full`
- Target: FPR drops from 88.2% → ≤40%. Report exact numbers.

### 2.4 AgentDojo (week 2-3)
- Install AgentDojo and Inspect Evals harness
- Register `KavachDefense` adapter
- Run workspace suite first (smallest, fastest)
- Then banking, travel, Slack suites
- Report: ASR, benign utility, utility-under-attack, per-call latency
- This is the must-have number for the paper. Target: ASR ≤ 5%.

### 2.5 OpenClaw-native staged attack (week 1-2)
- Run the 5-step cred→search→exfil attack scenario (in DELL_BENCHMARK_RUNBOOK.md)
- Capture ledger output showing traj_risk climbing and TRAJECTORY block firing
- Screenshot/export as paper figure evidence

---

## Phase 3 — Integration Sprint (both, weeks 4-5)

- Parv reports numbers from Phase 2
- Ishani fills §5 (Evaluation) of the paper with real benchmark data
- Build the comparison table (Kavach vs PRISM vs AgentArmor vs LlamaFirewall)
- Address the honest limitations in §7: mean-pooling chain ceiling (F1≤0.69 without trained model), single hook vs PRISM's 10, no tool-result provenance yet
- Merge all open PRs into `main` after verification
- Create anonymized artifact repo (anonymous.4open.science or GitHub anonymous link)
- Freeze the codebase for submission

---

## Phase 4 — Paper + Submission (weeks 5-7, deadline July 24)

### Target venue: AISec 2026
- **Deadline:** July 24, 2026 (firm, 23:59 AoE)  
- **Format:** 10 pages max, ACM double-column, anonymized, appendices don't count
- **Track:** Original Research or Benchmark Paper (if using Benchmark track: working artifact link required at submission time)
- **Submission site:** https://aisec26.hotcrp.com/
- **Required:** Explicit GenAI-use paragraph in paper (even if "GenAI was not used")
- **Notification:** September 3, 2026
- **Camera-ready:** September 16, 2026
- **Conference:** November 15-19, 2026, The Hague, Netherlands

### Paper section checklist

| Section | Status | Owner | Needs |
|---|---|---|---|
| §1 Introduction | 🟡 Draft | Ishani | Update with trajectory + AISec framing |
| §2 Background | 🟡 Draft | Ishani | Add ARM, Trajectory Guard, AgentDoG to related work |
| §3 Architecture | 🟡 Draft | Both | Add trajectory monitor diagram, ledger recovery |
| §4 Implementation | 🟡 Draft | Both | Update with v2 signals, embed-once refactor |
| §5 Evaluation | ⬜ Empty | Both | **Needs benchmark numbers from Phase 2** |
| §6 Related Work | 🟡 Draft | Ishani | PRISM diff, ZEDD diff, AgentWatcher diff |
| §7 Limitations | ⬜ Draft | Ishani | Mean-pooling ceiling, single hook, no tool-result provenance |
| §8 Future Work | ⬜ Empty | Both | Siamese trajectory model, tool-result provenance, SUPPLY/LEAKAGE ministers |
| §9 Conclusion | ⬜ Empty | Both | After §5 numbers exist |
| Artifact | ⬜ Not created | Ishani | Anonymous GitHub + README for reproducibility |

### Positioning statement for §1 (use this verbatim as a starting point):

> Kavach demonstrates that a single semantically-instrumented pre-execution hook,
> using BGE embedding similarity over a rolling session window, achieves high recall
> on direct and indirect prompt injection attacks against OpenClaw agents — without
> requiring lifecycle-wide instrumentation (PRISM: 10 hooks, ~15.8s p95 latency),
> trained trajectory models (Trajectory Guard), provenance graphs (ARM), or
> LLM-in-the-loop classifiers (LlamaFirewall: AlignmentCheck). The session-level
> trajectory monitor adds cross-call context — denial echo, sequential direction
> tracking, and cross-minister escalation patterns — enabling independent session
> blocks without a full provenance graph.

### Backup plan if July 24 is unreachable

If AgentDojo numbers aren't ready by July 10 (internal deadline to allow paper revision time), shift target to:
- **NeurIPS 2026 workshop** (non-archival, deadlines expected August-September 2026)
- Post to arXiv immediately to establish priority regardless of venue decision
- Hold AISec 2027 as the full polished submission

---

## Branch / PR Map

| Branch | What it contains | PR | Status | Who merges |
|---|---|---|---|---|
| `main` | Stable working code | — | — | — |
| `ishani/trajectory-monitor` | Trajectory v1+v2, embed-once, ledger traj_risk | PR #15 | Open — do NOT merge until Dell verified | Both verify |
| `ishani/fix-seed-intent` | Plugin seed_intent on session start (#9) | New PR | Ishani creates | Parv verifies live |
| `ishani/per-minister-thresholds` | Per-minister config + FPR fix (#3) | New PR | Ishani creates | Parv reruns InjecAgent |
| `ishani/agentdojo-adapter` | AgentDojo defense class | New PR or fold into above | Ishani creates | Parv runs |
| `parv/openclaw-native-bench` | OpenClaw-native 5-step attack scenarios | New PR | Parv creates | Ishani reviews |

**Merge order:** thresholds → seed-intent → agentdojo-adapter → trajectory-monitor → main

---

## What Success Looks Like

The paper can claim:

1. **Single-hook semantic interception:** 98.4% recall on InjecAgent (existing), ≤5% ASR on AgentDojo (needs Phase 2)
2. **Low latency:** measured p50=826ms / p95=1649ms vs PRISM's ~15.8s p95 — an order of magnitude faster; sub-second p95 remains a TARGET (not yet measured post embed-once), claim only measured numbers in the paper
3. **Session-level enforcement:** trajectory ceiling fires for multi-step attacks — denial echo catches causality laundering (ARM threat model), cross-minister escalation catches VAULT→CHANNEL chains (AgentDoG taxonomy)
4. **Low FPR:** ≤5% after per-minister thresholds (needs Phase 1.3 + Phase 2.3)
5. **OpenClaw-native:** the only semantic embedding-based monitor targeting OpenClaw's embedded-mode hook — distinct from PRISM (heuristic+LLM scanner), AgentWatcher (rule-based), and LlamaFirewall (not OpenClaw-specific)

---

## Open Issues Reference

| # | Title | Owner | Phase | Blocks |
|---|---|---|---|---|
| #2 | Hybrid BM25+dense retrieval (FPR fix) | Ishani | Future | — |
| #3 | Per-minister threshold support | Ishani | Phase 1.3 | FPR, InjecAgent rerun |
| #4 | Dynamic COMPASS-modulated thresholds | Ishani | Phase 1.3 (partial, trajectory does this) | — |
| #5 | AgentDojo benchmark runner | Parv | Phase 2.4 | Paper §5 |
| #6 | OpenClaw-native benchmark | Parv | Phase 2.5 | Paper §5 |
| #7 | EXECUTOR + VAULT corpus quality pass | Parv | Phase 2 (if time) | FPR |
| #8 | SUPPLY minister | Both | Post-submission | — |
| #9 | COMPASS session seeding fix | Ishani | Phase 1.2 | Escalation leg, trajectory ceiling |
| #15 | Trajectory monitor (this PR) | Ishani | Phase 1.1 | All of the above |
