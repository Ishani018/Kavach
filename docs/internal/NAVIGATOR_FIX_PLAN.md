# NAVIGATOR fix plan (branch `navigator-fixer`)

Why: the 100-case forced-format live-agent InjecAgent run (kavach-rearch
commit `466c9c9`, see
`benchmarks/results_v2/injecagent_live_results_template.md`) found
NAVIGATOR silently ALLOWed 39/81 real dispatched attacks — 90% single-step
(DH), clustering into three categories: financial-authorization abuse
(15), physical-access-control abuse (12), account-security tampering
(~10). Every one of the 39 misses was decided by the Speaker directly with
zero minister escalation, meaning NAVIGATOR's cosine-similarity corpus has
essentially zero coverage for these tool names — not a threshold-tuning
problem, a coverage problem.

Branched from `kavach-rearch` (not `main`), so it inherits everything from
that branch (the InjecAgent live-agent runner, the three runner bugs
fixed, `forced_tool_call.py`, the 100-case results). `main` and
`kavach-rearch` remain untouched stable checkpoints throughout this work.

## Phase 1 — Deterministic tier floor (✅ complete, generalization deliberately not patched)

`parliament/navigator_tiers.py`: a static classification table marks
specific tool names as TIER_3 (high-stakes/irreversible — default
ESCALATE) vs TIER_1 (everything else — unchanged ALLOW). Runs additively
alongside NAVIGATOR's existing cosine check (never replaces it) —
`speaker.py`'s existing most-restrictive-wins logic picks the stricter of
the two verdicts.

Result: 43/43 previously-missed dispatched attacker calls now correctly
ESCALATE. Regression check: 0/29 regressions against CHANNEL's existing
working `GmailSendEmail` read-then-send BLOCK detections — the tier floor
fires redundantly on those cases (harmless; CHANNEL's BLOCK still wins).

Commits: `959ba43` (tier floor + initial eval), `20f596d` (CHANNEL
regression check).

**Independent-generalization test result: 3/12 (25%) fired — all in the
financial category, and two of those three were coincidental substring
matches (`pay` matching inside "Payment"/"Payee"), not genuine coverage
of the actual verb. Physical and account-security categories had zero
regex coverage (0/4 each).** The original 43-case Phase 1 result was
100% exact-tool-name-match (0% via regex) — Phase 1's success was
hardcoded-list lookup against the exact benchmark it was built from, not
demonstrated generalization to novel tool names.

**Decision: do not patch the regex layer further.** A "light broadening"
pass was scoped (synonym alternation for the 9 specific misses — e.g.
`unlock|release|disengage|open`, `disable.*factor|mfa`, `deleterepo|
repodelete`) but deliberately **not applied**, because it would be
circular: hand-tuning the regex against the exact 9 examples that failed
would very likely score ~12/12 on this specific test purely because the
patch was reverse-engineered from it, telling us nothing about
generalization to a genuinely independent third set. This is the same
overfitting shape as Phase 1 itself, one level up.

**This is expected and by design, not a setback.** Phase 1 was always
scoped as the cheap, zero-LLM safety net — a deterministic floor that
converts known catastrophic misses into ESCALATE at near-zero cost, not
a system meant to reason about novel tool names. Pattern-matching on tool
names structurally cannot generalize the way task-conditioned reasoning
can, because authorization is a property of the TASK (does the user's
request license this specific action, on this specific target, right
now?), not a property the tool's NAME can encode no matter how the regex
is tuned. Phase 2's policy engine is the actual generalization
mechanism, specifically because it does not depend on tool-name pattern
matching at all — it reasons from the user's own task text.

## Phase 2 — Context-aware policy engine (⏳ not started)

`parliament/navigator_policy.py`: once-per-session LLM call (same
forced-JSON-schema technique as `forced_tool_call.py`) extracts a
structured policy from the user's original task — allowed payees, amount
ceiling, allowed devices/rooms/actuation types, explicitly-requested
security actions. Per-call deterministic enforcement (no LLM in the
per-call path) checks TIER_3 calls against that policy: a benign call
gets upgraded from Phase 1's ESCALATE to a definitive ALLOW when the task
licenses it; an unauthorized/injected call stays BLOCKed/ESCALATEd. Wired
into the Speaker with explicit precedence: policy layer gets first
refusal to resolve a Phase 1 ESCALATE; falls back to ESCALATE if
unresolved. Requires a latency check on real hardware before scaling
(once-per-session, not per-call, to stay within budget).

Not started — waiting on the generalization gaps above to be resolved
first, so Phase 2 is built on a tier floor that's confirmed to generalize
rather than one that only works on InjecAgent's exact tool names.

## Phase 3 — Full re-evaluation (⏳ not started)

Re-run the full 100-case forced-format sample (same seed) with the
complete hybrid NAVIGATOR (tier floor + policy layer). Report outcome
breakdown, tier-only vs. tier+policy ablation, FPR on the 17-case benign
pool (including resolution status of `benign_u16`/`benign_u11`), and a
CHANNEL DS-recall regression check. Package `forced_tool_call.py` +
`navigator_policy.py` for the Dell AgentDojo run with zero Kavach-specific
dependencies.

## Phase 4 — Paper writeup (⏳ not started)

Problem statement (39/81 miss, 90% single-step, category breakdown),
STEWARD reframing (the 0.0125 discriminability delta as a localizing
negative result — authorization is task-relative, structurally
unencodable in a single tool-call embedding — not a dead end), the
two-layer architecture citing Progent (arXiv:2504.11703) as the closest
external precedent (their AgentDojo ASR reduction, 39.9%→1.0%, cited as an
upper reference, not a claimed result for this work), results (before/after
table, ablation, FPR, AgentDojo), and limitations (deterministic-guaranteed
tier floor vs. best-effort single-LLM-call policy generation — no SMT
verification layer given the project timeline, stated as explicit future
work).
