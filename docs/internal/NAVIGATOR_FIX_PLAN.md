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

## Phase 1 — Deterministic tier floor (✅ complete)

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

## Generalization test (⚠️ found real gaps, not yet remediated)

Same methodology as the earlier VAULT/EXECUTOR corpus-expansion
independent test: 12 test instances (4 per category) using tool names
that are NOT InjecAgent names or paraphrases of them (e.g.
`StripeChargeCustomer`, `DoorLockRelease`, `MFADisable`,
`AccessPolicyOverride`).

**Result: 3/12 (25%) fired — all in the financial category. Physical and
account-security categories had zero regex coverage (0/4 each).** The
original 43-case Phase 1 result was 100% exact-tool-name-match (0% via
regex) — meaning Phase 1's success was hardcoded-list lookup against the
exact benchmark it was built from, not demonstrated generalization to
novel tool names.

Proposed (not yet applied) regex broadening:
- Physical: `(?i)(disarm|actuate|trigger|release.*lock|garage|opener)`
- Account-security: `(?i)(disable.*(factor|mfa|2fa)|mfa.*disable|share.*(password|credential)|credential.*share|delete.*repo|repo.*delete|permanent.*delete|override.*polic|polic.*override)`
- Financial: add `(?i)charge` to the existing family

These need to be applied and re-verified (both against the independent
test instances and the 32-case benign set, to check for new false
positives) before Phase 1 can be considered generalizing rather than
overfit.

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
