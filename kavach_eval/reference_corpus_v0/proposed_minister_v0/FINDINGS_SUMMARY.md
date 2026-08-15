# STEWARD Scoping — Findings Summary (revised plan)

Status: **investigation/design only.** Nothing in this branch is wired into
`parliament/`, nothing touches `kavach_corpus_v1.json` or the live
`.chroma_kavach` store. `kavach_corpus_v1_ORIGINAL.json` MD5 verified
unchanged at every step: `7ce71ec38c9bdd2f273a34205c13fc5e`.

## The headline finding

**STEWARD as a 5th static-pattern-matching minister does not work — proven,
not assumed.** A discriminability test (`discriminability_test_RESULTS.json`)
took 3 real AgentDojo matched pairs (same tool, same argument shape, one
legit/user-requested version and one injected/malicious version) and found
legit vs. injected scored almost identically against STEWARD's draft
patterns (mean delta +0.0125 — within embedding noise). The two versions of
each call were 0.90–0.94 similar *to each other*. The call's text genuinely
does not encode whether it was authorized — no amount of better patterns or
more training data fixes this, because the discriminating signal (which
specific recipient/file/value the user actually named) isn't present in the
call text at all.

A follow-up test (`option_a_compass_test_RESULTS.json`) checked whether
COMPASS's existing session-intent-drift mechanism (same embedding-similarity
approach, different comparison target) fares any better. It doesn't, mostly:
2 of 3 pairs showed no separation; the one pair that did separate turned out
to be a lexical coincidence (the user's prompt happened to contain the exact
literal password string), not evidence the mechanism actually understands
authorization.

**Conclusion: this category needs structured constraint-matching against
session-specific facts (Option B, PAuth-style), not embedding similarity in
any form.**

## Option B feasibility (investigated, not built)

Design work identified 3 constraint types a session-intent extraction step
would need to support: **literal** (a value named directly in the user's
instruction — cheap, deterministic, no new infrastructure), **provenance**
(a value must trace back to a specific source the user named — needs
visibility into prior tool-call results, which Kavach does not have today),
and **runtime-binding** (a value is computed by a tool call during the
session, e.g. "the largest file" — needs the same missing infrastructure
plus per-tool re-derivation logic).

Traced Kavach's actual integration paths to assess how hard that missing
infrastructure would be to add:
- **AgentDojo**: no new hook needed. `KavachDefense` already receives the
  full message history, including prior tool results — it just isn't
  reading them today. This is an extraction-logic change, not new wiring.
- **InjecAgent**: cannot support this at all. It's a static single-shot
  replay harness with no live tool execution and no session — there is no
  tool result to ever become visible.
- **OpenClaw (the real production target)**: doesn't have a blocking
  `before_tool_call` hook yet (pending upstream PRs #5513/#5943). Current
  integration (`kavach_monitor.py`) is post-hoc only. Tool results already
  flow through the session transcript Kavach reads, just aren't extracted.

Storage cost for structured session data is small (sampled real AgentDojo
tool results: median 467 chars, well under 100KB per session at the
existing 12-action window) and doesn't threaten `trajectory.py`'s
sub-millisecond embed-once budget — it's an additive, parallel data
structure, not a change to the existing fast path.

## The classification pass — this is what actually changes the plan

Went looking for every real matched legit/injected pair in AgentDojo's own
suites (not just the original 3) to see how the 3 constraint types actually
distribute across real cases. **InjecAgent's 62 cases could not be included
— they have no paired legitimate task and no live execution, so there is
nothing to classify.** This pass covers AgentDojo's full injection-task set:
24 tasks across banking/slack/travel/workspace with a real `ground_truth`
tool call (one task, travel InjectionTask6, has no tool call at all and was
excluded).

| bucket | count | share | what it actually needs |
|---|---|---|---|
| **literal** | 6 | 25% | Option B, cheap tier — no new infrastructure |
| **provenance** | 4 | 17% | Option B, expensive tier — needs tool-result visibility |
| **runtime-binding** | 1 | 4% | Option B, expensive tier — needs the same infrastructure plus per-tool re-derivation logic |
| **exfiltration-shaped** | 9 | 38% | **Not STEWARD's job at all.** These are `search/read → send/post to attacker` pairs — CHANNEL's existing territory. CHAN-102 (already drafted, confirmed clean fit, ready to merge) covers this shape directly. |
| **doesn't fit any of the 3 types** | 4 | 17% | Neither STEWARD nor Option B. 2 are magnitude/structuring attacks ("send as much as possible," split transfers to dodge a threshold) — need a check over amounts/behavior patterns, closer to `trajectory.py`'s existing accumulation/chain signals. 2 are content-safety attacks (phishing URLs) — need a check over what content itself is, closer to EXECUTOR/CHANNEL's existing pattern-based checks. |

Total genuinely Option-B-shaped: **11/24 (46%)**, and less than half of that
(6/24, 25%) is the cheap tier.

## Revised plan

1. **Merge CHAN-102** (already drafted, `patterns.json`) — covers 38% of
   real cases identified, no new infrastructure, no new minister, extends
   an existing clean-fit pattern into CHANNEL. Cheapest, highest-coverage
   move available.
2. **Build the literal constraint type only, first** — covers another 25%,
   still no new infrastructure (per the AgentDojo integration finding
   above). A real, shippable increment before committing to anything larger.
3. **Defer provenance + runtime-binding** — the 21% they'd add requires
   the tool-result-visibility infrastructure this investigation scoped but
   did not build. Treat as separate future work with its own decision
   point, not an assumed follow-on to step 2.
4. **The remaining 17% (magnitude/structuring, content-safety) needs
   neither STEWARD nor Option B** — flag as a distinct problem for
   `trajectory.py` (behavioral/magnitude signals) and the existing
   pattern-based ministers (content-safety checks) to pick up separately,
   not folded into this workstream.

## Where everything lives (this branch)

- `proposed_minister_v0/design_proposal.md` — STEWARD minister design draft,
  external corroboration (OWASP, BOLA taxonomy paper, MITRE ATT&CK ICS, CWE)
- `proposed_minister_v0/patterns.json` — 6 draft STEWARD patterns +
  CHAN-102 (ready-to-merge)
- `proposed_minister_v0/discriminability_test_RESULTS.json` — the test that
  falsified STEWARD-as-pattern-matcher
- `proposed_minister_v0/option_a_compass_test_RESULTS.json` — the test that
  ruled out extending COMPASS as-is
- `proposed_corpus_additions_v0.json` — the original 62-case InjecAgent
  clustering that motivated the STEWARD proposal in the first place
- `injecagent_attack_matches_RAW.json` — raw similarity-matching data from
  the corpus-gap analysis
- This file — the 24-task AgentDojo classification and revised plan
