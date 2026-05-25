# Kavach — 4-Week Conference-Readiness Plan

**Status:** Browser lab works. Post-hoc monitor works. No real-time interception. No benchmark numbers. No proof of generalization.

**Goal:** By end of Week 4, Kavach is a real guardrail (not a monitor), with InjecAgent F1/FPR numbers, a calibrated threshold derived from data, and a paper skeleton ready to fill in.

**Single most important thing:** Fix OpenClaw bugs #5513 and #5943 so `before_tool_call` actually fires. Until this is done, everything else is decoration.

---

## The honest state

| Claim | Real | Proven |
|---|---|---|
| "Kavach is a guardrail" | No — it's a monitor (catches attacks after they run) | No |
| "Parliament catches novel attacks" | Maybe | No (corpus was written staring at ClawHavoc) |
| "Ministers are independent" | Probably partially correlated | Never measured |
| "F1 / FPR / latency numbers" | None exist | — |
| "Browser embedding lab" | Yes | Yes — works end-to-end |
| "Research positioning vs DeepContext / TraceSafe / LlamaFirewall" | Yes | Yes — solid lit review done |

---

## The four parallel workstreams (4 weeks)

### Workstream A — Real-time interception (Parv + Ishani)
**The most important workstream.** Without this, Kavach is a post-hoc audit log.

- Week 1: Reproduce bug #5513 on a fresh OpenClaw checkout. Document the silent no-op.
- Week 1–2: Apply the lazy-getter fix from observability-plugin PR #6 (ISI-515). Wire `before_tool_call` into `executeToolCalls()` per #5943's reference patch. Write vitest regressions.
- Week 2: Open PR-1 to OpenClaw upstream. Comment on Discussion #9872.
- Week 2–3: Write the OpenClaw plugin (`openclaw-plugin-kavach`) that registers on `before_tool_call`, sends the tool name + args to the parliament HTTP endpoint, and acts on the verdict.
- Week 3: End-to-end test: run a ClawHavoc-style attack against an OpenClaw agent with the Kavach plugin installed; confirm the action is denied before execution, not after.

**Deliverables:**
- `openclaw_pr/PR1_hooks_fix.md` — patch spec
- `openclaw_pr/PR1_test_5513.ts`, `PR1_test_5943.ts` — vitest tests
- `plugin/openclaw-plugin-kavach.ts` — the plugin
- `plugin/openclaw.plugin.json` — manifest

### Workstream B — Real Python parliament service (Ishani)
The browser lab proves the logic. Now make it a service the plugin can call.

- Week 1: Stand up `parliament/server.py` as a FastAPI process bound to `127.0.0.1:8088`.
- Week 1: Port the five-collection ChromaDB query path from `corpus_loader.py`. Use BGE mean pooling. Asymmetric query prefix.
- Week 2: Implement the speaker logic from the browser lab as `parliament/speaker.py`. Same thresholds.
- Week 2: Add `/hook/parliament`, `/hook/seed_intent`, `/hook/check_drift`, `/health`, `/ledger/votes`. Same wire format the existing demo server uses, so `kavach_monitor.py` keeps working.
- Week 3: Add a circuit breaker (3 consecutive failures → 60s open) and a fail-mode flag in the response. Required for production-grade plugin behavior.

**Deliverables:**
- `parliament/server.py`
- `parliament/ministers.py`
- `parliament/speaker.py`
- `parliament/config.yaml`

### Workstream C — Kill the overfitting problem (Janya + Pranitha)
The current corpus was written while staring at ClawHavoc. The system is doing sophisticated keyword matching, not semantic understanding. Fix this before any benchmark run, or the numbers are meaningless.

- Week 1: Read `corpus_v2/expansion_protocol.md` (in this folder). Internalize the rules.
- Week 1: Each person writes 50 new pattern descriptions per minister, drawn **only from MITRE ATT&CK technique IDs and OWASP Agentic 2026 categories** — never from a CVE, never from a known attack you've seen.
- Week 2: Cross-review. Anyone who can identify which writer wrote which pattern means the patterns are too writer-specific. Rewrite.
- Week 2: Re-embed the corpus. Run the COMPASS calibration tab on the embedding lab — actually compute Youden's J, don't accept gut-feel thresholds.
- Week 3: Run 50 benign agent sessions through the parliament. Measure FPR. If above 5%, the system is not ready for any benchmark and patterns need pruning.

**Deliverables:**
- `corpus_v2/expansion_protocol.md` — the discipline
- `corpus_v2/new_patterns_*.json` — 100 new patterns total (25 per minister)
- `corpus_v2/benign_traces.jsonl` — 50 benign sessions
- A calibrated threshold per minister, derived from data not gut

### Workstream D — Get real numbers (Janya, Week 3–4)
Once interception is wired and the corpus is honest, run the benchmark.

- Week 3: Write `benchmarks/injecagent_runner.py`. Reads InjecAgent's 1,054 test case JSON. Sends each through the parliament HTTP endpoint. Records verdict + latency.
- Week 3: Run it. Plot precision/recall ROC curves.
- Week 4: Write `benchmarks/threshold_sweep.py`. Sweep thresholds 0.30 → 0.85. Plot ROC. Derive optimal per-minister threshold from curves.
- Week 4: Write up results. These become Section 5 of the paper.

**Deliverables:**
- `benchmarks/injecagent_runner.py`
- `benchmarks/threshold_sweep.py`
- `benchmarks/results_v1.csv` (numbers)
- `benchmarks/roc_curves.png` (figure for paper)

---

## Paper skeleton (Workstream E, written in parallel by Jamieboy, all 4 weeks)

`paper/skeleton.tex` is the structural skeleton. Fill in numbers as Workstream D produces them.

- §1 Introduction — problem (agent attack surface), three contributions (parliament, COMPASS, temporal-vs-spatial)
- §2 Background — agent infrastructure, attack surface, existing guardrails (LlamaFirewall, AgentSpec, AGrail, ShieldAgent, CaMeL)
- §3 Kavach architecture — parliament, four ministers, COMPASS, ledger, detective
- §4 The temporal-vs-spatial defense-in-depth distinction — formal claim, theorem statement, why this is novel vs LlamaFirewall
- §5 Evaluation — InjecAgent results, COMPASS calibration, FPR on benign traces, latency budget
- §6 Related work — differentiation paragraphs vs DeepContext, TraceSafe, LlamaFirewall, AgentSpec, AGrail, ShieldAgent, CaMeL, FIDES, RTBAS, Conseca, Task Shield
- §7 Limitations — the overfitting story (honest), single-vector cosine ceiling per Trajectory Guard, no AgentDojo yet
- §8 Future work — CORTEX activation probes, SUPPLY minister, federated corpus, MCP-Security spec

---

## What we are NOT doing

These are good ideas. They are not for this 4-week window.

- CORTEX (activation probes) — ROI high but premise is "interception works", which it doesn't yet
- SUPPLY minister — same reason
- Touching the browser lab — it's done. Don't fiddle
- AgentDojo — too complex for first benchmark run; do InjecAgent first
- A new hook RFC for `before_delivery` — `message_sending` already exists in the SDK, file payload-extension PRs against the existing hook later, not now
- Rewriting the speaker as generator-evaluator (the research report's recommendation) — this is paper-worthy work for v2, not for this submission

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| OpenClaw maintainers reject PR-1 (bugs #5513, #5943) | Low — they're documented bugs | Frame as additive bug fix with regression test; cite the lazy-getter precedent from observability-plugin PR #6 |
| InjecAgent recall is below 60% | Medium — overfitting risk is real | Workstream C is precisely the mitigation; run cold (no corpus tuning to InjecAgent) and report honestly |
| FPR on benign traces above 10% | Medium | If true, it's a paper finding worth reporting — current state of guardrail field |
| Parliament latency >300ms p95 | Low | BGE-base is ~25ms per query; five collections in parallel; should hit <100ms |
| Maintainer ships a different security hook design upstream while we're in flight | Low | Kavach's HTTP wire format is framework-agnostic; ship an OpenClaw-shape adapter if needed |

---

## The single sentence

The single most important thing the team can do right now is fix the two OpenClaw bugs so `before_tool_call` actually fires — because until that's done, Kavach is a monitor not a guardrail, and everything else is decoration. Everything after that — benchmarks, new ministers, the paper — follows naturally once interception is real.
