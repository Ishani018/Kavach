# Proposed 5th Minister — Design Draft (NOT wired into Parliament)

Status: **proposal only**. No changes to `parliament/`, `kavach_corpus_v1.json`,
`config.yaml`, or `run_minister_hybrid`. This document and the accompanying
`patterns.json` are for review by the user and Parv before any implementation
work starts.

## 1. Why a 5th minister

The 62-case InjecAgent gap analysis (`kavach_eval/reference_corpus_v0/proposed_corpus_additions_v0.json`)
found that 6 of 7 identified attack-intent clusters were weak fits for all four
existing ministers. Reviewing the existing architecture:

| minister | what it actually detects |
|---|---|
| EXECUTOR | *how* code executes (shell construction, dynamic eval, injection into interpreters) |
| VAULT | *what* gets read (credential files, env vars, secret stores) |
| CHANNEL | *where* data goes (outbound exfil mechanism — HTTP, email, DNS, clipboard, etc.) |
| NAVIGATOR | *whether behavior drifts* from the stated task (reconnaissance beyond scope, safety-mechanism bypass, post-completion persistence) |

All four are **mechanism-focused**: they detect a technical pattern in *how* an
action is carried out. None of them reason about the **real-world consequence**
of an action that is technically unremarkable — a single, correctly-formed API
call to a tool the agent legitimately has access to, where the call itself
looks like normal tool use. `BankManagerTransferFunds(amount=3000, account=X)`
is not shell injection, not credential theft, not a novel exfil mechanism, and
not behavioral drift in the NAVIGATOR sense (the agent didn't do anything
*extra* — it did exactly the one thing the injected instruction asked, in a way
that looks identical to a legitimate user-authorized action). The attack lives
entirely in *what the action means*, not in how it's technically constructed.

This is a distinct detection axis, not a gap that can be closed by adding more
patterns to NAVIGATOR — it needs a minister whose L1/L2/L3 vocabulary is built
around **action consequence and reversibility**, not syntax or data flow.

## 2. Proposed name and scope

**Name: STEWARD**

(Mnemonic: a steward acts on your behalf and is judged by whether their
actions serve your actual interests — the semantic opposite of what these
attacks exploit.)

**Scope statement:** STEWARD evaluates whether a tool call, if executed,
would produce a real-world consequence (financial, physical, access-control,
or data-integrity) that exceeds, contradicts, or was not authorized by the
user's actual current request — regardless of whether the call itself is
syntactically unremarkable or uses a tool the agent has legitimate access to.

**What makes STEWARD distinct from the other 4:**
- EXECUTOR/VAULT/CHANNEL ask "is this technically dangerous machinery?" —
  STEWARD asks "is this action's *effect* something the user actually wanted?"
- NAVIGATOR asks "does the agent's *behavior pattern* deviate from the task?" —
  STEWARD asks "does this *single action's consequence* deviate from what was
  authorized?", which can fire on the FIRST and ONLY call in a session (no
  behavioral pattern needed), unlike most NAVIGATOR patterns which inherently
  need session history to detect drift.
- STEWARD is intent/consequence-shaped (L1 is about outcome), not syntax-
  shaped (L3 across EXECUTOR/VAULT/CHANNEL is code/API-call-shaped text).

## 3. Split decision: one minister, not several

Considered splitting into financial-harm vs. physical-harm (or more) ministers.
**Decision: keep it as one minister (STEWARD) with 6 categories**, matching
how the existing ministers already differentiate internally via the
`category` field (e.g. NAVIGATOR already spans `process_enumeration`,
`vm_aware_evasion`, `instruction_disclosure` — very different technical
flavors under one minister).

Reasoning:
- The *detection mechanism* is identical across all 6 categories: "does this
  action's target/effect match what the user actually authorized in this
  session." A fund transfer to an unauthorized IBAN and an unauthorized
  smart-lock unlock are structurally the same check (destination/effect not
  named by the user), just applied to different tool domains.
- Splitting multiplies operational surface (more thresholds to calibrate, more
  BM25/dense collections to maintain, more Speaker routing logic) for a
  benefit that doesn't materialize — you would not gain any detection power
  by separating them, since the underlying signal and matching logic are the
  same.
- If in practice one category (e.g. `unauthorized_fund_transfer`, which has
  the strongest evidence base with 6 InjecAgent + 9 AgentDojo banking cases)
  turns out to need materially different tuning than the others, it can be
  split out later — starting unified and splitting on evidence is lower-risk
  than starting split and discovering the categories don't actually behave
  differently enough to justify separate thresholds.

**Uncertain / flagging for judgment call:** `physical_world_disruption_iot`
(traffic lights, emergency dispatch, home robots) has zero AgentDojo
corroboration — AgentDojo has no smart-home/IoT/physical-actuator task suite,
so this category rests entirely on the 5 InjecAgent cases. It's the weakest-
evidenced category in the set. Worth discussing whether it belongs in v0 at
all, or should wait for a second data source.

## 4. Threshold — placeholder, NOT calibrated

Existing thresholds and what they're calibrated against:

| minister | threshold | basis |
|---|---|---|
| EXECUTOR | 0.55 | Dell-validated against templated + red-team paraphrase eval |
| CHANNEL | 0.60 | same |
| NAVIGATOR | 0.70 | same |
| VAULT | 0.75 | same (highest — VAULT patterns are narrowly specific, so a tighter threshold avoids FPs on lower-specificity generic reads) |

**Proposed STEWARD threshold: 0.65 (placeholder, uncalibrated)**

Reasoning for this starting point, not a measurement:
- STEWARD is semantically closer to NAVIGATOR (intent/consequence-based, not
  syntax-based) than to EXECUTOR/CHANNEL (technical-surface-based), so it
  should not start at EXECUTOR's low 0.55 — L1-intent-only matching without
  L3 syntax backup tends to be noisier and needs more margin.
- It should not start as high as VAULT's 0.75 either — VAULT's patterns are
  extremely narrow/specific (a handful of well-known credential file paths),
  which supports a tight, well-separated threshold. STEWARD's L1 intent
  descriptions ("transfer funds to an unauthorized destination") are broader
  categories covering many different real tool names, closer to NAVIGATOR's
  breadth.
- 0.65 sits between CHANNEL (0.60) and NAVIGATOR (0.70) as a reasonable
  starting midpoint. **This number has zero empirical backing** — it has not
  been run through the FP-probe validator, the benign-traffic replay, or any
  threshold sweep. Treat it as "don't block anything below this until it's
  actually measured," not a real calibration.

**This needs the same validation pipeline as the existing 4** (benign probe
FP gate, dedup gate, detection-sim gate from `kavach_eval/corpus_agent/`)
before any real number should be trusted — none of that was run here, this
is drafting only.

## 5. Pattern coverage summary

7 patterns total: 6 new STEWARD patterns + 1 CHANNEL addition (CHAN-102,
already-confirmed clean fit, drafted ready-to-merge separately from STEWARD).

**Updated after an external-source corroboration pass** (OWASP API Security
Top 10, the BOLA-in-the-wild empirical taxonomy paper [arXiv:2605.25865,
verified real], MITRE ATT&CK for ICS, and CWE) — see
`patterns.json`'s `external_source_pass` block and each pattern's
`external_corroborating_sources` field for full citations/quotes.

| id | category | InjecAgent | AgentDojo | new external sources | evidence strength |
|---|---|---|---|---|---|
| STEW-001 | unauthorized_fund_transfer | 6 | 9 | +1 (BOLA paper, real Cosmos SDK bug-bounty disclosure) | strong — 3 independent sources |
| STEW-002 | unauthorized_access_grant | 3 | 0 | +1 (OWASP BFLA canonical example) | **moderate — closed from single-source this pass** |
| STEW-003 | unauthorized_destructive_modification | 7 | 2 | +2 (BOLA paper Mozilla disclosure; OWASP BOLA doc-deletion scenario) | strong |
| STEW-004 | physical_world_disruption_iot | 5 | 0 | +3 (MITRE ATT&CK ICS T0831 + real 2008 Lodz tram incident; T0813; OWASP BOLA vehicle-VIN scenario) | **moderate — closed from single-source this pass, first real independent-domain (ICS) corroboration** |
| STEW-005 | security_control_weakening | 4 | 1 | +1 (CWE-862, real CVE-2009-2960) | strong |
| STEW-006 | session_service_disruption | 2 | 1 | **+0 — no corroboration found in any of the 4 new sources** | still weakest — flagged below |
| CHAN-102 | sensitive_data_exfil_via_legit_retrieval | 35 | 0 | not in scope for this pass (not a STEW category) | strong, CHANNEL fit already confirmed clean |

**Result: STEW-002 and STEW-004 both moved from single-source to
multi-source this pass.** STEW-004 in particular now has its first
corroboration from an entirely independent domain (real industrial-control-
system attacks, not just LLM-agent benchmark scenarios) — the 2008 Lodz tram
incident (unauthorized replayed control signals causing 4 derailments and 12
injuries) is a real-world precedent for "unauthorized command to a physical
control system," the same underlying pattern as InjecAgent's traffic-control/
emergency-dispatch cases. **STEW-006 remains the only fully single-source-
plus-AgentDojo category with zero external corroboration** — none of OWASP/
BOLA-paper/ICS/CWE's scopes cover "unauthorized channel-membership churn,"
which is a narrower and more collaboration-tool-specific concept than the
other 5 categories.

## 6. Open questions for user/Parv review

1. **Is STEWARD the right scope, or should this be folded into NAVIGATOR
   after all** with an explicit acknowledgment that NAVIGATOR's definition
   broadens to include consequence-based single-call detection, not just
   multi-call behavioral drift? A 5th minister is a bigger architectural
   commitment (new collection, new threshold, new Speaker wiring, new BM25
   index, new eval harness support) than expanding NAVIGATOR's stated scope.
2. **STEW-004 (physical/IoT) now has real independent corroboration**
   (MITRE ATT&CK for ICS, a named technique family with real-world incident
   precedent), which meaningfully strengthens its evidence base — but Kavach's
   threat model has otherwise been "an LLM agent misusing software tools,"
   not "an LLM agent controlling physical actuators," and ICS attacks are a
   different attacker/access model than prompt-injection-driven LLM misuse.
   The pattern is better-evidenced now; whether it's the right threat model
   for *this* system is still a separate, open question.
3. **STEW-006 (session/service disruption) has no external corroboration**
   after checking 4 additional sources — it may be too narrow/domain-specific
   a category to warrant its own pattern; consider folding it into STEW-003
   (destructive modification) as a milder variant, as originally flagged.
5. **Threshold 0.65 is a placeholder** — needs a real calibration pass
   (FP-probe gate, dedup gate, detection-sim gate, ideally a small red-team
   pass) before being trusted for anything beyond directional experimentation.
6. **The "one call, no history needed" detection model is new** for this
   system — STEWARD would be the first minister that can fire meaningfully
   on a single isolated tool call with no session context. Worth confirming
   the Speaker/routing logic doesn't assume all ministers need session
   history before this goes further.
