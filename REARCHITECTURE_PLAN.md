# Kavach re-architecture plan: from cosine-similarity ministers to domain-specialized detectors

Status: **scoping only, no detection code written.** Branch
`rearchitecture-v0`, branched off `steward-scoping-v1`'s tip
(`b5f7669`). `main` untouched throughout (confirmed at `9e00ac4`
before and after this work).
`kavach_corpus_v1_ORIGINAL.json` MD5 confirmed unchanged:
`7ce71ec38c9bdd2f273a34205c13fc5e`.

This plan synthesizes two inputs: (1) the research artifact from this
session (embedding-anisotropy literature, RouteGuard, AuthGraph/DRIFT/
CaMeL, production-guardrail survey, and the follow-up Q&A on originality,
per-minister designs, and RAG placement) and (2) my own direct reading of
`parliament/ministers.py`, `server.py`, `speaker.py`, `trajectory.py`,
`provenance.py`, and `kavach_router_config.json` — every architectural
claim below is checked against the real running code, not assumed from
the research artifact's own (also codebase-grounded, but independently
written) analysis. Where the two disagree or where I found something the
research artifact didn't cover, it's flagged explicitly.

**Every prior finding this session (the banking catch-rate inflation, the
LOLBIN/CHAN-102 audit, the BGE-M3/decoupled-retrieval/scope-router
investigations) is direct empirical evidence for this plan's core
premise** — four independent attempts at fixing detection *within* the
cosine-similarity architecture (model swap, hybrid retrieval variants,
decoupled candidate selection, a structural scope-router) each failed a
rigorous test. This plan is the first attempt to fix the architecture
itself rather than tune around it.

---

## 1. The swap point: is `MinisterScan` really the clean boundary?

**Confirmed, with one real caveat the research artifact didn't fully
resolve.**

Read `parliament/server.py`'s `/hook/parliament` handler directly
(lines 597-716). The exact call site for every minister is:

```python
run_minister_hybrid(minister, req.text, collection, bm25_idx,
                     _embed_query, m_thresholds, 10, action_vec) -> MinisterScan
```

`MinisterScan` (dataclass, `ministers.py:53-62`) is:
```python
minister, verdict, confidence, matched_id, matched_text, matched_level,
source=None, retrieval_mode="dense"
```

Everything downstream — `combine_verdicts()` in `speaker.py`,
`traj.record_action()` in `trajectory.py`, `provenance.resolve()`, and
the SQLite ledger — consumes only this struct's fields. **Confirmed
directly**: `speaker.py`'s `combine_verdicts()` reads `r.verdict`,
`r.confidence`, `r.minister`, `r.matched_id`, `r.matched_level` and
nothing else minister-internals-specific. This means each minister's
`run_minister_*` function can be replaced by an arbitrary detector — a
regex scanner, an AST walker, a taint tracker — as long as it returns a
`MinisterScan` with a real verdict and confidence. **This part of the
research artifact's claim is correct and directly verified.**

### The real caveat: `confidence` is used for more than the verdict

Three places downstream treat `confidence` as a **calibrated real-valued
score**, not just a tiebreak for the BLOCK/ESCALATE/ALLOW label:

1. **`speaker.py`'s dynamic threshold re-evaluation** (`_reapply_thresholds`,
   lines 122-155) re-derives the verdict from `r.confidence` against a
   COMPASS-modulated effective threshold — it does **not** trust the
   verdict a minister already computed; it recomputes it from the raw
   confidence number. A deterministic detector (regex/AST/taint) that
   returns a binary hit/no-hit needs to map onto this same continuous
   scale, or `_reapply_thresholds` will silently re-derive a different
   verdict than the detector intended (e.g. a regex hit reported as
   `confidence=1.0` would always survive re-evaluation regardless of
   COMPASS drift, which may or may not be the desired behavior for a
   deterministic hit — this is a real design decision the plan needs to
   make explicitly, not inherit from the embedding-based semantics by
   accident).
2. **`trajectory.py`'s `ActionRecord.confidence`** (used in the
   `accumulation` signal, `W_ACCUMULATION=0.35`) treats confidence as a
   decayed risk accumulator across a session. A deterministic detector's
   binary hit needs a confidence value here too, or the accumulation
   signal silently degrades for calls that used to contribute graduated
   risk and now only contribute 0.0 or 1.0.
3. **`trajectory.py`'s `denial_echo` signal** (lines 29-34, threshold
   `DENIAL_ECHO_THRESHOLD=0.68`) compares the **current action's
   embedding** against a previously-denied action's embedding — this is
   cosine similarity over `action_vec`, **not** `MinisterScan.confidence`
   at all. This signal survives the minister rework untouched regardless
   of what a minister's internals become, because it operates on the
   shared `action_vec` from the embed-once step, independent of which
   minister produced the block. **Flagging this precisely because the
   research artifact's Q&A section said trajectory.py is "fine to keep
   as one factor among several" without distinguishing which of
   trajectory's five signals depend on minister confidence (accumulation,
   escalation) vs. the shared action embedding (chain, denial_echo) vs.
   the minister's own decided_by name (minister_esc) — they have
   different dependencies and need different handling.**

**Resolution for the plan**: deterministic detectors return a
`confidence` on the same `[0,1]` scale as today, with a documented
convention — e.g. a hard rule match (regex/deny-list hit) reports
`confidence = 1.0` (equivalent to the strongest possible cosine match
today), and "no rule fired" reports `confidence = 0.0`, letting the
existing threshold/accumulation machinery work unchanged. This is a
real but small design decision, not a blocker — flagged here so it's
made deliberately in Stage 2's design, not discovered as a bug later.

### Other things that would break the clean-swap assumption, checked directly

- **`run_minister_dual_hybrid`** (referenced at `server.py:647`, used
  when a minister has a "tech" collection) — a second code path beyond
  `run_minister_hybrid`. Not fully read in this pass; **flagged as
  needing the same swap-boundary check before Stage 2 touches any
  minister that currently uses the dual-corpus path** (confirmed at
  least CHANNEL does, from this session's CHAN-102 work).
- **`retrieval_mode` field** (`"dense"` / `"hybrid"`) is reported in
  `MinisterResult` back to the API caller and presumably logged. A
  deterministic detector isn't "dense" or "hybrid" — needs a third value
  (e.g. `"deterministic"`) added to keep the field honest, a trivial
  change but worth listing so nothing silently mislabels itself as
  embedding-based after the swap.
- **`matched_text`** is used for human-readable justification strings in
  `speaker.py`'s `reason` field (e.g. `"{winner.minister} matched
  {winner.matched_id} ({winner.matched_level}) at sim {winner.confidence}"`).
  A regex/AST hit needs to populate this with something meaningful (the
  matched pattern name, the flagged AST node, the taint path) — not hard,
  but the `reason` string's wording literally says "at sim" which stops
  being accurate for a non-similarity detector. Cosmetic but worth fixing
  so audit logs don't lie about the mechanism.

---

## 2. Per-minister target design (ROI/feasibility order)

Order matches the research artifact's own ranking, cross-checked against
the actual tool surface Kavach screens (confirmed via this session's
banking live-run: `send_money`, `update_password`,
`schedule_transaction`, `get_most_recent_transactions`, etc. — real
AgentDojo tool calls, not hypothetical).

### 2.1 VAULT — deterministic credential-path/secret-format rules (do first)

**Borrowed, not novel**: regex patterns for `.env`, `.aws/credentials`,
`id_rsa`, `.ssh/`, `.pem`, cloud key formats (`AKIA...`, GCP service
account JSON shape). The research artifact's suggestion to borrow
gitleaks/truffleHog's maintained pattern sets rather than write from
scratch is sound — these are mature, community-maintained regex
libraries with known false-positive characteristics already tuned by a
much larger user base than Kavach could replicate.

**What's genuinely Kavach's own**: the **taint tag** on credential
reads — marking a value as "sourced from a credential path" so a later
CHANNEL check can catch it if that value tries to leave the session.
This is the piece connecting VAULT to CHANNEL's taint-tracking design
(§2.3) — not a gitleaks feature, since gitleaks scans static repos, not
live session data flow.

**No model needed.** Confirmed feasible in microseconds per call.

### 2.2 EXECUTOR — AST-based parsing + LOLBIN deny-list (second)

**Borrowed**: the deny-list itself (`os.system`, `subprocess.*`, `eval`,
`exec`, LOLBIN command names like `certutil`/`regsvr32`/`bitsadmin` —
this session's own LOLBIN test set is a real, already-built source for
validating this list). Python's `ast` module for parsing is standard
tooling.

**What's genuinely novel** (per the research artifact's own framing,
which I agree with after reading `ministers.py`'s current text-only
approach): **security-specific dataflow rules over the parsed tree**,
not generic linting:
- Resolved call names (so `import os as o; o.system(...)` is caught,
  not just literal `os.system` substring match) — this directly fixes
  a class of evasion the *current* cosine-similarity EXECUTOR minister
  cannot address at all, since it only sees raw text.
- Decode-then-exec dataflow: does a `base64.b64decode(...)` call's
  output feed into an `exec`/`eval` call in the same tree? This requires
  tracing data flow through the AST, not just flagging both function
  names independently.
- Command-string construction tracing (string concatenation/formatting
  feeding into `subprocess`) — the LOLBIN obfuscation pattern this
  session's own `test2_lolbin.py` results show the current cosine
  ministers catch inconsistently (23.1%→38.5% across two embedding
  variants, never above 40%).

For **shell commands** (not Python), `shlex`-based parsing + the LOLBIN
deny-list, with chain-detection (`;`, `&&`, `|`) flagging a network tool
following a file-read tool in the same chain — this is a real, small
piece of novel dataflow logic (source→sink shape) layered on top of
borrowed tooling (`shlex` itself).

**No model needed for the deterministic path**; escalate genuinely
ambiguous cases to an LLM judge only if Stage 2's evaluation shows a
real residual gap (see §5).

### 2.3 CHANNEL — symbolic taint tracking (third)

**Borrowed conceptually**: the taint-tracking *model* (Denning 1976
lattice, realized in agent contexts by CaMeL/arXiv:2503.18813,
FIDES/arXiv:2505.23643, NeuroTaint/arXiv:2604.23374 — all confirmed real
in the prior BGE-M3/best-of-both/decoupled-retrieval investigations this
session already did deep literature verification on, cross-referenced
against `related_work_comparison.md` from earlier in this branch's
history). The general pattern (tag untrusted sources, flag tainted-data
→ untrusted-sink flows) is not Kavach's invention.

**What's genuinely Kavach's own**: applying this specifically to the
**tool-call graph** as Kavach observes it (via the same session
`messages` history `KavachDefense.query()` already receives but doesn't
currently parse for taint, per the design work in this session's
`provenance_tier/DESIGN.md`), plus a **destination allow/reputation
list** for outbound sinks specific to the tool surfaces Kavach screens
(banking IBANs, Slack channels, email domains — not generic network
taint tracking).

**No model needed** — symbolic propagation over the tool-call graph,
confirmed feasible without embeddings or an LLM.

**Direct connection to this session's own evidence**: CHAN-102 (already
merged to production, verified clean by direct re-audit this session,
§`catch_rate_audit/AUDIT.md` on `steward-scoping-v1`) is a **cosine
pattern** approximating exactly this read-then-send taint shape. Its
70.0% catch rate (up from 63.3%) is real, but it's still approximating a
structural property (data flow) with a similarity heuristic. A true
taint tracker should **strictly dominate** CHAN-102's coverage since it
checks the actual data-flow property CHAN-102's corpus text can only
gesture at — this is a concrete, falsifiable claim Stage 2's evaluation
(§6) should test directly: does the taint-tracking CHANNEL replacement
catch every case CHAN-102 catches, plus more?

### 2.4 NAVIGATOR — AuthGraph/DRIFT-lite plan-vs-execution check (hardest, highest value)

**This is the piece that directly answers this session's single most
important finding**: the original discriminability test (`send_money(
recipient=alice)` vs. `send_money(recipient=attacker)` scoring
0.90-0.94 cosine similarity to each other) proved structurally that no
amount of corpus tuning fixes authorization-attack detection under a
cosine-similarity architecture. Every subsequent attempt this session
(BGE-M3 swap, best-of-both, decoupled retrieval, the deterministic
provenance tier, the scope-router) was, in one way or another, still
operating within or adjacent to that same architecture. NAVIGATOR's
redesign is the first one that changes the actual detection mechanism
for this specific problem class.

**Design** (matches DRIFT/arXiv:2506.12104's Secure Planner + Dynamic
Validator shape, and AuthGraph/arXiv:2605.26497's clean-context
extraction, both already scoped in detail in this branch's
`option_b_build_analysis.md` from earlier session work — this plan
reuses that scoping rather than re-deriving it):

1. **At task start** (once, not per call): `qwen2.5:7b`, in a
   clean/injection-free context (the user's original task text only,
   confirmed available via `KavachDefense.query()`'s `query` parameter
   per `benchmarks/kavach_agentdojo_defense.py`, read directly earlier
   this session), extracts a structured authorization plan: an expected
   tool-call checklist and, for each WRITE-type/security-critical
   parameter, either a literal authorized value or "must trace to tool
   X's output."
2. **At each call**: cheap, deterministic structural comparison — no
   LLM, no embedding — of the actual call's arguments against the
   extracted plan. This is **exactly** the mechanism already designed
   and unit-tested this session in `provenance_tier/DESIGN.md` (the
   literal-value-mismatch + session-history-substring-match check,
   validated against real synthetic cases including the
   `update_password` clean-fix case).

**Important, honest connection to prior findings this session already
established** (must not be silently re-litigated): the Option B
ablation (`ablation_v0/ABLATION_RESULTS.md`, committed earlier on
`steward-scoping-v1`) already tested almost exactly this mechanism
end-to-end on 26 real AgentDojo cases and found it was a **wash**, not a
clear win, against ministers-only — 6 vs. 7 truly-discriminating cases,
traced to one specific, fixable date-format normalization bug in the
extractor's equality check. **This plan does not get to claim NAVIGATOR
as an automatic win** — it inherits that ablation's exact finding and
its exact fix (date/time-aware value comparison, not exact-string
equality) as a known prerequisite before NAVIGATOR's redesign can be
declared successful. Re-running that ablation with the bug fixed is a
concrete, already-scoped Stage 2 evaluation task (§6), not new work to
invent.

**No model needed per call** — only once per task, confirmed feasible
per this session's own live qwen2.5:7b banking run (task-start plan
extraction is a single generation, not the per-call bottleneck; the
per-call structural comparison after that is pure Python).

### 2.5 Novel vs. borrowed, summarized

| minister | borrowed | Kavach-specific/novel |
|---|---|---|
| VAULT | gitleaks/truffleHog-style regex patterns | taint tag on credential reads feeding CHANNEL |
| EXECUTOR | `ast` module, LOLBIN name lists | resolved-call-name tracing, decode-then-exec dataflow, shell-chain source→sink detection |
| CHANNEL | taint-tracking model (Denning 1976, CaMeL/FIDES/NeuroTaint lineage) | applied to Kavach's specific tool-call graph + destination allow-list for the actual tool surfaces screened |
| NAVIGATOR | AuthGraph/DRIFT clean-context-extraction pattern | the specific literal/provenance/runtime-binding constraint taxonomy already built and partially validated this session (Option B), applied to Kavach's session/ledger architecture |

---

## 3. The router: fail-open preservation + RouteGuard finding

**Fail-open confirmed directly in the running code**, not assumed:
`server.py:213-215` —
```python
if not activated:
    log.info("router: no minister crossed %.2f, falling back to all four", threshold)
    return list(_state["router"].keys())
```
A routing miss (no minister crosses `router_min=0.40`) already falls
back to activating all four ministers, not zero. **This property must be
preserved unchanged through every stage of this plan** — it is the
single most important safety property in the current design, and none
of the proposed minister-internals swaps touch `_route()` at all, so
this is low-risk to preserve as-is through Stage 1 and Stage 2.

**RouteGuard finding (arXiv:2605.30693), independently verified this
session** (not re-verified in this pass, but the research artifact's
citation is consistent with the earlier `related_work_comparison.md`/
`landscape_strategy.md` verification standard already established on
this branch's history — treated as reliable): kNN/embedding routers
collapse to 16.97 F1 out-of-domain vs. 48.55 in-domain, which is why
RouteGuard uses a fine-tuned generative LLM router instead. **This is a
real, direct threat to Kavach's current router**, which is exactly an
embedding/cosine router (`_route()`'s `_cosine(q, doc_vec)` over
`kavach_router_config.json`'s domain descriptions). The fail-open
fallback partially mitigates the failure mode RouteGuard found (a
misroute under Kavach's design still results in "run all four ministers"
rather than RouteGuard's "return empty verdict set") — this is a
structural advantage Kavach's fail-open design already has over
RouteGuard's union-of-experts design, worth stating explicitly as a
point of differentiation (§7).

**Decision for this plan**: keep the existing embedding router
unchanged for Stage 1 and Stage 2, exactly as the research artifact
recommends, because (a) the fail-open fallback already bounds the
downside of a routing miss to "extra minister calls," not "unscreened
attack," and (b) Stage 2's minister-internals swaps are independent of
routing correctness — a WRITE-type call needs to reach NAVIGATOR whether
routing picked it via cosine similarity or an LLM classifier. **Router
replacement is explicitly deferred to Stage 3**, gated on a real,
measured routing-miss rate from Stage 1/2 evaluation data, not done
speculatively alongside the minister rework.

---

## 4. Provenance mapping gap — resolved more cleanly than expected

Read `parliament/provenance.py` in full (255 lines). The research
artifact's second-pass analysis flagged this as an open gap ("if
ministers stop producing corpus matched_id/source... you'll need to
decide how deterministic detections map to ATT&CK/CWE"). **Direct
reading of the code shows this gap is smaller than that framing
suggests:**

`provenance.resolve(source: str | None, minister: str) -> Provenance`
takes exactly two inputs — `source` (a corpus pattern's tagged source
string, e.g. `"MITRE ATT&CK T1552.001"`) and `minister` (a plain string
name, e.g. `"VAULT"`) — and:
1. Regex-parses an ATT&CK/ATLAS technique ID, CWE ID, or OWASP-Agentic
   category out of `source` if present (`_ID_RE`, `_CWE_RE`,
   `_OWASP_RE`).
2. **Falls back to a per-minister default technique** (`_MINISTER_DEFAULT`,
   e.g. `VAULT → "T1552"`) when `source` has no parseable ID —
   confirmed this fallback exists specifically for exactly the case a
   deterministic detector produces: a match with no corpus-pattern
   provenance string at all.

**This means a deterministic detector needs to supply only a `source`
string in the same tagged format** (e.g. a VAULT regex rule for
`.aws/credentials` could set `source="MITRE ATT&CK T1552.001"` directly,
since that's a real, already-mapped technique ID in `_TECH`), **or
supply nothing and rely on the existing minister-default fallback**,
which the code already treats as an honest, labeled case
(`provenance_basis="minister-default"`, not silently blank). No changes
to `provenance.py` itself are needed for Stage 1 or Stage 2 — the
integration point is simply: every new detector's returned
`MinisterScan.source` field should be set to the relevant ATT&CK/CWE/
OWASP tag when the rule/AST-check/taint-flow has an obvious one (most
will — e.g. an `os.system` deny-list hit maps directly to
`"CWE-78"`/`T1059`, a credential-path regex hit maps directly to
`T1552.001`), falling back to the per-minister default otherwise.

**One real gap, not addressed by the existing code**: `_MINISTER_DEFAULT`
is a single fixed technique per minister. Once EXECUTOR/VAULT/CHANNEL/
NAVIGATOR each run several distinct deterministic rules (not one cosine
match against one corpus), a single default technique per minister
under-specifies which specific rule fired. **Recommendation**: each new
detector rule should carry its own explicit `source` tag (a small,
hand-built table, same pattern as the scope-router's `TOOL_CATEGORY`
table from this session's `scope_router/DESIGN.md` — confirmed
low-effort since the rule set itself is already being hand-built for
Stage 2 regardless) rather than relying on the coarse per-minister
fallback for everything. This is new work, but small — a lookup table
alongside each rule set, not a change to `provenance.py`'s resolution
logic.

---

## 5. Staging, with independent shippability

Each stage leaves Kavach fully working end-to-end — confirmed against
the real pipeline flow (`server.py:597-716`) for exactly where each
stage's changes land.

### Stage 1 — additive deterministic pre-filters (lowest risk)

**What changes**: new checks added to the `/hook/parliament` handler,
running **alongside** the existing ministers (not replacing anything) —
VAULT-style credential-path regex and EXECUTOR-style dangerous-call
deny-list, evaluated on every call regardless of routing (per the
research artifact's "cheap universal pre-filters bypass the router
entirely" recommendation, which I agree with: these are near-free and
should not depend on the embedding router's correctness at all). A hit
from either pre-filter contributes an additional signal into
`combine_verdicts()` — simplest implementation: treat it as a synthetic
`MinisterScan` with `confidence=1.0`, `retrieval_mode="deterministic"`,
alongside whatever the real ministers return, so it flows through the
existing veto-fusion logic (`speaker.py`'s "any single BLOCK is
sufficient") unchanged.

**What does NOT change**: `_route()`, minister internals, `speaker.py`'s
combination logic, `trajectory.py`, `provenance.py`'s resolution
function, the ledger schema. This is why it's lowest risk — it's purely
additive.

**Expected effect, grounded in this session's own evidence, not
speculation**: the banking live-run found ministers-alone catching
81.2%→85.2%-shaped numbers were substantially driven by false-positive
blocks on benign reads, while genuinely missing real WRITE-call attacks
(`send_money` scored `ALLOW` even when co-occurring reads got flagged).
A deterministic EXECUTOR/VAULT pre-filter targeting the actual
attack-relevant call shapes directly, rather than broad cosine
similarity, should reduce exactly this false-positive pattern — this is
the same directional finding the scope-router prototype
(`scope_router/DESIGN.md`, this session) already demonstrated
empirically on real trajectories (FP rate 66.7%→33.3% under a
write-only structural filter). Stage 1 formalizes and extends that
finding into production-shaped detectors rather than a scope-limiting
router.

### Stage 2 — replace minister internals one at a time

Order: VAULT → EXECUTOR → CHANNEL → NAVIGATOR (§2's ROI ordering).

**What changes, per minister**: the `run_minister_hybrid(...)` call site
for that one minister is swapped for a new function with the same
`MinisterScan`-returning signature. Confirmed from `server.py:639-671`
that ministers are already invoked in a loop over `activated` (the
router's output) via `run_in_executor` — swapping one minister's
function is a one-line change per minister at that call site, with no
change to the loop structure, `asyncio.gather`, or any other minister's
invocation.

**What does NOT change, per swap**: every other minister's internals,
`speaker.py`, `trajectory.py` (once the confidence-scale convention from
§1 is fixed once, at the start of Stage 2, not per-minister),
`provenance.py` (per §4), the ledger. **Each minister's swap is
independently testable and independently revertable** — if VAULT's
regex replacement underperforms on evaluation (§6), only VAULT reverts;
EXECUTOR/CHANNEL/NAVIGATOR are unaffected because they're separate call
sites returning the same struct shape.

### Stage 3 — router upgrade, gated on evidence

Only pursued if Stage 1/2 evaluation shows a real routing-miss rate
(attacks reaching zero or the wrong minister) above a threshold — not
done speculatively. Two options already named by the research artifact,
both real and available: semantic-router's `HybridRouter` (dense+sparse,
lower engineering cost) or a `qwen2.5:7b` "which ministers?" classifier
prompt (RouteGuard's validated architecture, higher engineering cost but
stronger OOD evidence). **Given this session's own repeated finding that
BGE-M3/sparse-hybrid retrieval changes underperformed on held-out data
in three separate investigations** (`bge_m3_investigation/`,
`decoupled_retrieval/` on `steward-scoping-v1`), the LLM-router option
should be the default hypothesis for Stage 3, not the hybrid-embedding
option, unless Stage 1/2 data specifically shows routing misses are rare
enough that a cheaper fix suffices. This is a real, evidence-grounded
bias worth stating now rather than re-deriving after another embedding
variant fails the same way the last three did.

---

## 6. Evaluation plan — attributable, non-inflatable

Directly addresses the exact failure mode this session found and
audited (banking catch-rate inflation, `catch_rate_audit/AUDIT.md`).

### The core methodological fix

**Measure whether the block landed on the actual malicious call, not
"any call in the trajectory got flagged."** This session's own audit
established the precise diagnostic: trace each "catch" to the specific
tool call that triggered it, and separately check whether that call is
the one the attack's own success condition depends on (AgentDojo's
`security()` field, confirmed this session to mean "True = injection
goal achieved," or the equivalent ground truth for the attack case). A
catch driven by an unrelated benign call in the same trajectory does not
count as detection.

### Per-minister-swap evaluation, before/after

For each Stage 2 swap, measure on the **same held-out set**, before and
after:
1. **Precision on a NotInject-style benign set** — tool calls containing
   attack-adjacent tokens/shapes that are legitimate (e.g. a real
   `get_most_recent_transactions` read, a real credential-path access
   for a legitimate backup script) — this directly targets the
   over-defense failure mode PIGuard/NotInject document and this
   session's banking run empirically found (66.7% FP rate on 3 real
   benign tasks under ministers-alone).
2. **Recall on held-out real attack cases** — using cases NOT used to
   design or tune the specific detector being evaluated, per the
   anti-overfitting discipline already established and validated this
   session (`decoupled_retrieval/VERDICT.md`'s tuning/held-out split
   methodology, which caught a real overfitting result on the decoupled
   candidate-selection prototype — the same discipline must apply here,
   not be relaxed because this is a "bigger" change).
3. **Both measured with the corrected, per-call-traced catch metric**
   (not trajectory-level "any flagged"), so a swap's reported
   improvement cannot be inflated the way the original 85.2% ministers
   number was.

### Held-out set candidates, already available in this repo

- `attacker_cases_ds.jsonl` (32 cases, confirmed zero tool overlap with
  `attacker_cases_dh.jsonl` in the decoupled-retrieval investigation) —
  reusable as a genuinely untouched held-out attack set for Stage 2's
  evaluation, since it was never used to tune any minister's rules.
- The Option B ablation's 26-case AgentDojo set (`ablation_v0/`) for
  NAVIGATOR specifically, since it already has the literal/provenance/
  runtime-binding classification needed to evaluate NAVIGATOR's plan-
  check mechanism precisely.
- A NotInject-style benign set does **not** yet exist in this repo and
  needs to be built — real tool calls with attack-adjacent shapes/tokens
  that are legitimate. This is genuinely new work (flagged, not hidden),
  though the banking live-run's own benign trajectories
  (`get_most_recent_transactions` called repeatedly, `send_money` to a
  real biller IBAN) are a real, already-collected starting seed set, not
  a from-scratch build.

---

## 7. RouteGuard differentiation (for the eventual related-work section)

Honest, not defensive — the overlap is real and must be cited, not
argued away.

**Real overlap**: both route to specialized detectors instead of one
monolithic guardrail; both union/fuse expert verdicts (RouteGuard unions,
Kavach's speaker veto-fuses — same family); both are concerned with
routing-miss/fail-open behavior.

**Real differences, each concrete and checkable against the code, not
just asserted**:
1. **Domain taxonomy**: RouteGuard's experts are content-safety
   categories (Agent Safety, Cybersecurity, Physical Harm, Non-Violent
   Misconduct, Social Risks) — general LLM-guardrail domains, still
   scoring *text* for safety. Kavach's ministers (EXECUTOR/VAULT/
   CHANNEL/NAVIGATOR) are specifically about agent tool-call execution,
   mapped to MITRE ATT&CK/OWASP Agentic categories via the real,
   already-shipping `provenance.py` taxonomy (§4) — a materially
   different problem space (runtime enforcement vs. content
   moderation).
2. **Mechanism diversity, not just different classifier weights**: this
   is the plan's actual point — RouteGuard's experts are all trained
   classifiers/guard models (Qwen3Guard variants) scoring text, i.e. the
   same detection *mechanism* repeated per domain with different
   training data. Kavach's post-rework ministers are mechanistically
   different from each other — regex, AST/dataflow, taint-propagation,
   authorization-graph comparison — because different attack classes
   are structurally different problems, not different vocabularies of
   the same problem. This is the concrete, falsifiable novelty claim
   Stage 2's evaluation needs to substantiate, not just assert.
3. **Pre-execution interception with real side effects**: Kavach gates
   actual tool calls before they execute (confirmed directly:
   `KavachDefense.query()` intercepts inside AgentDojo's
   `ToolsExecutionLoop` and can suppress execution by returning a
   refusal `ChatToolResultMessage` — read directly this session,
   `benchmarks/kavach_agentdojo_defense.py`). RouteGuard, per its own
   paper, classifies input/output text for safety — it is not described
   as gating tool execution with real-world consequences. This is a
   different point in the agent pipeline with different stakes for a
   false negative.
4. **Timing**: RouteGuard is a May 2026 preprint — very recent, must be
   cited regardless of the above differences, and cannot be presented as
   unaware of it.

**What this means for the paper, stated plainly (consistent with this
session's own standing instruction to prioritize honesty over
optimism)**: "route to specialized detectors" cannot be claimed as
Kavach's novel contribution — RouteGuard published that pattern, and the
MoE-guardrail literature generally predates both. The defensible
novelty, once Stage 2 actually ships, is the combination of (a) the
agent-tool-call-execution domain specifically, (b) genuine per-domain
*mechanism* diversity rather than a repeated classifier, (c) pre-
execution interception with real side effects, and (d) whatever Stage
6's evaluation shows that RouteGuard's own paper doesn't measure (their
in-domain gain over monolithic guards was modest, ~+0.4 F1; their OOD
gain was real, +6.7 F1 — Kavach's evaluation should report the
equivalent comparison honestly, including if it turns out similarly
modest in some dimension).

---

## Summary: what Stage 1 buys before any minister-internals work starts

Per the research artifact's own flagged tradeoff (echoed independently
in its Q&A: "Stage 1 alone might be enough to ship for the deadline"),
worth restating plainly since it's a real, low-risk, high-signal first
move: Stage 1's additive deterministic pre-filters require **zero
changes** to the existing minister/speaker/trajectory/provenance/ledger
pipeline, are independently revertable, and directly target the exact
false-positive and missed-authorization patterns this session's banking
live-run and scope-router prototype already demonstrated empirically —
not a hypothetical improvement, a re-application of a result already
measured this session at smaller scale.

## Limitations (documented, not TODOs — real gaps found during Stage 2 builds)

- **CHANNEL's destination allow-list cannot distinguish self-directed from
  attacker-directed data sharing for Slack and banking.** No analogous
  verified-identity field exists in AgentDojo's environment model for
  either suite (Slack has no "which user am I" marker at all; banking's
  `BankAccount.iban` is not semantically distinguished from a recipient
  IBAN) — this is a permanent limitation absent a new identity source
  invented outside AgentDojo's own model, not something Kavach can wire
  around. **Fixed for the workspace/email-destination case**: AgentDojo's
  `Inbox.account_email` (a real, populated, per-task identity) is now
  passed through via an optional `account_email` field on the
  `/hook/parliament` request's existing `context` dict and wired into
  `channel_taint.py`'s destination check — a destination call to the
  session's own `account_email` no longer taints/blocks on that basis
  alone, while a genuinely different (attacker-controlled) destination
  still does. Re-validated: all 3 originally-constructed "send sensitive
  data to self" cases now correctly ALLOW when `account_email` is
  provided and the destination matches it, while continuing to BLOCK when
  it doesn't (confirmed via the real `/hook/parliament` API, not just the
  standalone module) — and Slack/banking destination tools are confirmed
  unaffected (no exemption leak; presence of `account_email` in context
  does not suppress a Slack/banking taint block).

## Open decisions for the next conversation (not resolved by this plan, by design — this doc scopes, it doesn't decide)

1. Confidence-scale convention for deterministic detectors (§1) — a
   concrete design choice needs to be made once, before Stage 2 starts,
   not per-minister.
2. Whether Stage 1's timeline fits before any submission deadline this
   work is being done against (the research artifact's Q&A flagged this
   explicitly; this plan doesn't know the deadline and shouldn't guess).
3. Per-rule provenance-source tagging effort (§4) — small but real new
   work, needs to be scoped alongside each minister's Stage 2 rule set,
   not deferred silently.
4. The NotInject-style benign set (§6) needs building — real work, not
   yet started, needed before Stage 2's first evaluation can run.
