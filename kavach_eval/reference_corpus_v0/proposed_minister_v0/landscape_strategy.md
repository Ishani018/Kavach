# Landscape strategy: positioning Kavach + Option B in a crowded 2026 field

Status: research + strategy synthesis, nothing built or changed. Saved to
`steward-scoping-v1`, `main` untouched. Builds on `related_work_comparison.md`
and `option_b_build_analysis.md`. Every paper/system below was independently
verified real (arXiv fetch or GitHub/docs fetch, quoted where load-bearing)
before being used in any argument — no claim below rests on unverified
recall. Where a claim from the prompt could not be confirmed as stated,
that is reported explicitly rather than smoothed over.

`kavach_corpus_v1_ORIGINAL.json` MD5 confirmed unchanged throughout:
`7ce71ec38c9bdd2f273a34205c13fc5e`.

**One correction to the premise up front:** the survey "From Agent Traces
to Trust" (arXiv:2606.04990, confirmed real, v4 dated June 28 2026) does
**not** mention AuthGraph, FORGE, DRIFT, Progent, or AgentArmor anywhere in
its text — checked directly against the full HTML. It is a real, relevant,
well-constructed taxonomy, but it is an **accountability/auditing-framed**
survey (its own words: "process-level accountability," "verification,
attribution, debugging, safety enforcement, audit, failure attribution,
recovery"), not a defense-specific survey, and it only covers CaMeL, Fides,
NeuroTaint, and AgentSentry from the list in the prompt. It is the spine
for *part* of this landscape, not all of it — the enforcement-camp systems
(AuthGraph, FORGE, DRIFT, Progent) needed to be independently verified and
slotted in by hand. This is a useful correction to make now rather than
build the paper's related-work section on a premise that doesn't survive
a direct check.

---

## Part 1 — The landscape, mapped

### 1.1 The survey's actual taxonomy (arXiv:2606.04990)

Six dimensions (their Table 1, confirmed via direct quote):

1. **Trace sources** — reasoning, retrieval, tool use, MCP boundaries,
   memory, environment, multi-agent communication
2. **Evidence and execution units** — semantic objects (evidence: what
   supports/contradicts a claim) vs. procedural objects (execution: what
   the agent did)
3. **Provenance relations** — support, derive, depend-on, contradict,
   invalidate, trigger, update, use, generate
4. **Granularity/timing** — run-level to token/span-level;
   pre-execution/runtime/post-hoc/continuous
5. **Representation forms** — structured logs, execution graphs, evidence
   graphs, claim-support graphs, provenance graphs, runtime state
6. **Trust functions** — verification, attribution, debugging, safety
   enforcement, audit, failure attribution, recovery

Confirmed, this survey's central organizing principle (their exact words,
Section 4.3) is the one the prompt named:

> "The key lesson is that unsafe behavior can arise from influence, not
> content alone. A webpage may be safe to summarize but unsafe if an
> embedded instruction determines an email recipient, database parameter,
> or authorization signal."

This is real and it is the right principle — it's a more general statement
of exactly what our own discriminability test demonstrated empirically for
`send_money(recipient=X)`.

**Where the four survey-covered systems land, per their own taxonomy
(Section 4.3, direct quotes):**

| system | arXiv | mechanism (their words) | trust function |
|---|---|---|---|
| CaMeL | 2503.18813 | "isolates control flow from data flow… restricting how external data can influence agent behavior" | runtime safety enforcement |
| Fides | 2505.23643 | "formalizes agent-level information-flow control through confidentiality and integrity labels enforced during execution" | runtime safety enforcement, formal guarantees |
| NeuroTaint | 2604.23374 ("Ghost in the Agent") | "propagates taint across neural and symbolic components," "including through semantic transformations" | **post-hoc audit** (offline trace analysis, not runtime blocking — confirmed via a second source: "audits execution traces offline") |
| AgentSentry (survey's exemplar, distinct from the AgentSentry paper 2602.22724 we already had — see note below) | — | "tracks the sources of values flowing into sensitive tool arguments, demonstrating why parameter-level lineage is needed beyond tool-level permission checks" | runtime safety enforcement |

**Important naming collision, worth flagging explicitly:** the survey's
"Agent-Sentry" exemplar (parameter-level lineage tracking) is described in
a way that does **not** match the "AgentSentry" paper we already verified
in `related_work_comparison.md` (arXiv:2602.22724, "temporal causal
diagnostics," masked re-execution / counterfactual dry-run mechanism —
our "Option C"). These may be the same system described two different
ways, two different systems with similar names, or the survey may be using
"Agent-Sentry" generically. This was not resolved by the fetches available
here and should be checked before citing both in the same paper without
disambiguating — citing them as if obviously the same system, or obviously
different, would both be unverified claims.

### 1.2 The enforcement-camp systems (not in the survey, independently verified)

| system | arXiv | mechanism (one line) | guarantee | stated cost/limitation |
|---|---|---|---|---|
| **AuthGraph** | 2605.26497 | Dual-graph: clean-context authorization graph (Planner, GPT-4o-mini) vs. execution-trace reasoning graph (GPT-4o), aligned by a Checker (GPT-4o) | empirical (94-97% ASR reduction on AgentDojo/AgentDyn), not formal | same-observation pollution (if the authoritative source itself is compromised, the check passes anyway); 3 LLM roles, 2 frontier-tier, real per-task latency (Checker 1.33s, AG-gen 2.20s, RG-gen 1.12s per their Table 6) |
| **CaMeL** | 2503.18813 | Privileged LLM plans; Quarantined LLM (no tool access) processes untrusted data; custom interpreter enforces capabilities before each tool call | **provable** (Control Flow Integrity-style) | utility drop — 0.48 vs. AuthGraph's 0.69 on the same benchmark (AuthGraph's own Table 3, confirmed) |
| **Fides** | 2505.23643 | IFC confidentiality/integrity labels, formal noninterference (integrity) + explicit secrecy (confidentiality) | **formal**, strongest of the group | first paper to give formal guarantee statements for this problem class — implies the guarantees are new/hard-won, likely at real utility/expressiveness cost (not independently re-derived here, would need a dedicated read of 2505.23643 to quote their own utility numbers) |
| **NeuroTaint** ("Ghost in the Agent") | 2604.23374 | Semantic-transformation-aware taint tracking; explicitly designed because "traditional taint analysis... fundamentally fails" on probabilistic NL reasoning | empirical, offline | **post-hoc/offline only** — audits traces after the fact, does not block in real time; outperforms Fides on source-sink detection per TaintBench (400 scenarios, 20 frameworks) |
| **DRIFT** | 2506.12104 | Secure Planner (minimal function trajectory + parameter checklist) + Dynamic Validator (deviation monitoring) + Injection Isolator (masks conflicting instructions in memory) | empirical | AuthGraph's own Table 3: ASR 0.03 vs. AuthGraph's 0.01, A.UR 0.45 vs. AuthGraph's 0.44 (DRIFT is close to AuthGraph here — the two are structurally similar, "Secure Planner + parameter checklist" reads as a close cousin of AuthGraph's "Planner + ParamPolicy") |
| **Progent** | 2504.11703 | Symbolic privilege-control rules over tool names/args, LLM-assisted policy generation | empirical, deterministic enforcement once policy is set | AuthGraph's Table 3: ASR 0.02 (close to AuthGraph) but **A.UR 0.03** — near-total utility collapse under attack, meaning Progent's policies block almost everything once an attack is detected, a real and citable precision/recall tradeoff distinct from AuthGraph's |
| **FORGE** | 2602.16708 | Datalog-based declarative policy enforcement at the action boundary; "first to combine expressiveness, dependency tracking, multi-agent support, and deterministic enforcement in a single design" (their own claim) | deterministic, no baseline numbers found in the fetches available here | not independently benchmarked against AuthGraph in what was retrieved — would need direct comparison, not assumed |
| **AgentArmor** | 2508.01249 | Converts full runtime trace into program-analysis IRs (CFG/DFG/PDG), applies a type system with taint tracking | static-analysis-style guarantees over the trace | heaviest-weight of the group — "treat the entire trace as an analyzable program," per our own earlier framing in `related_work_comparison.md` |

**AuthGraph's exact comparison numbers (their Table 3, confirmed via direct
quote), AgentDojo/GPT-4o-mini:**

| defense | ASR | UR (utility) | A.UR (utility under attack) |
|---|---|---|---|
| AuthGraph | 0.01 | 0.69 | 0.44 |
| CaMeL | 0.00 | 0.48 | 0.32 |
| Progent | 0.02 | 0.64 | 0.03 |
| DRIFT | 0.03 | 0.52 | 0.45 |

AuthGraph's own claim, quoted: "the only defense that simultaneously
achieves ASR ≤ 0.01 and UR ≥ 0.69." This is real, and it is a legitimately
strong result — CaMeL has marginally better ASR but a 21-point utility
drop; Progent's utility-under-attack collapses to near-zero; DRIFT is
close on both axes but slightly worse on each.

### 1.3 OpenClaw-specific work (verified, real, live)

**VeriGrey (arXiv:2603.17639, "Greybox Agent Validation")** — confirmed
real, and directly tests OpenClaw. Uses mutation-fuzzing on injection
prompts, chaining the injection task to the agent's actual task so the
injection becomes load-bearing for task completion. Reported: 10/10
malicious-skill discovery on Kimi-K2.5, 9/10 on Opus 4.6, run against
OpenClaw specifically. A quote from secondary coverage worth citing
directly (not from the paper itself, but a strong independent framing of
the same point our discriminability test makes):

> "prompt injection is no longer just a content moderation issue—it is an
> authorization problem disguised as a language problem."

**"awesome-agent-skills-security" — correction:** the closest real match
found is `VoltAgent/awesome-openclaw-skills` (5,400+ skills, categorized,
includes a security-and-passwords category and general warnings about
prompt injection/tool poisoning in third-party skills). This is a skills
*directory* with security awareness built in, not a dedicated security
research list as the name in the prompt implied. Real and relevant to cite
for "the OpenClaw skills ecosystem has known injection risk at scale," but
should not be cited as if it were a curated academic-style security survey.

Independent corroboration of scale: Snyk's ToxicSkills study (not an
arXiv paper, a vendor blog, cited for the number only) found prompt
injection in 36% of scanned ClawHub skills, 1,467 confirmed malicious
payloads. This is directional industry evidence, not peer-reviewed, and
should be labeled as such if cited.

---

## Part 2 — Where Kavach actually sits

### 2.1 Kavach today (no Option B): detection/gate camp, not provenance camp

Kavach's current architecture — 4 pattern-matching ministers (EXECUTOR,
VAULT, CHANNEL, NAVIGATOR) doing hybrid BM25+BGE retrieval against a
static corpus, plus COMPASS (session-intent cosine drift) and
`trajectory.py` (accumulation/escalation/chain/denial-echo/cross-minister
signals over a bounded action window) — is a **detection/gate system**,
structurally closer to a WAF or an anomaly-detection layer than to any of
the systems in §1. None of CaMeL/Fides/NeuroTaint/AuthGraph/DRIFT/Progent/
FORGE do anything resembling embedding-similarity-against-a-curated-corpus
matching; all of them reason about *provenance of specific values*, which
Kavach's 4 ministers structurally cannot do — this is exactly what our own
discriminability test proved (§ of `related_work_comparison.md`,
`discriminability_test_RESULTS.json`): pattern-matching cannot distinguish
`send_money(recipient=legit)` from `send_money(recipient=attacker)`
because the call text alone doesn't encode authorization.

**This is not a weakness unique to Kavach** — it's the exact gap the
"influence, not content" principle (§1.1) describes, and it's why every
system in §1.2 exists at all. Kavach's 4-minister layer is good at a
different, real problem (does this call's *technical mechanism* look like
a known attack pattern — shell injection, credential-file reads, exfil
mechanics) that provenance-only systems don't directly address either.
AuthGraph's own Layer 1 ("Hard Block") and Layer 2 (tool-sequence
whitelist) are comparatively coarse next to Kavach's hybrid BM25+BGE
matching against a 400+-pattern corpus with MITRE ATT&CK grounding — the
systems in §1.2 are not typically evaluated on "how well do you recognize
a known malicious shell one-liner," because that's not the problem they're
solving.

### 2.2 What adding Option B moves Kavach toward

Option B (literal/provenance/runtime-binding constraint extraction,
scoped in `option_b_build_analysis.md`) is structurally the same idea as
AuthGraph's `ParamPolicy` + source-check, confirmed field-by-field in
`related_work_comparison.md`. Building it moves Kavach's *provenance*
handling from "none" to "AuthGraph-adjacent, narrower scope" — it does
**not** turn Kavach into a competitor to CaMeL or Fides, which enforce
formal or architectural guarantees (control/data separation,
noninterference) that no amount of Option B construction gets us; those
are different engineering commitments (a custom interpreter, a type
system) than "extract constraints, check them against tool-call
arguments."

**Honest positioning: Kavach + Option B would be a *lighter, narrower*
reimplementation of AuthGraph's core mechanism, bolted onto a
pattern-matching layer AuthGraph doesn't have.** That combination —
not either half alone — is the actual differentiation candidate. Whether
it's a *sufficient* one is the harder question below.

### 2.3 Brutally honest: what does Kavach + Option B do that AuthGraph doesn't, and vice versa

**What AuthGraph does that we don't and can't cheaply match:**
- Tool-call **sequence** whitelisting (their Layer 2), which we haven't
  scoped at all.
- A **formal isolation property** for the extraction step (their Property
  1) — we can adopt the same architecture (clean-context extraction) but
  we have not attempted, and likely cannot cheaply attempt, an
  information-theoretic proof of it; we'd be relying on the same
  informal "seed_intent fires before any tool call" argument we already
  had.
- Two frontier-tier LLM roles (GPT-4o for Graph Builder and Checker) doing
  real reasoning over the full trajectory every task. Our design, scoped
  for a CPU-only laptop and a small local model (`qwen2.5:7b`), is
  necessarily doing less reasoning per check — this is a real capability
  gap, not just a cost optimization; a 7B model doing string-match-first
  extraction is not the same reasoning quality as GPT-4o doing LLM-fallback
  judgment on ambiguous cases, and our own overnight prototype's
  non-determinism finding is direct evidence of this gap in practice.
- A demonstrated 94-97% ASR reduction on two real benchmarks. We have not
  built or measured an equivalent number for Option B at all yet — the
  6.2-6.4% CHAN-102 improvement (63.3%→70.0%) is a pattern-matching-layer
  result, not a provenance result, and shouldn't be conflated with what
  Option B would need to demonstrate on its own.

**What Kavach has that AuthGraph doesn't:**
- The 4-minister technical-mechanism detection layer — real coverage of
  attack *shapes* (shell injection, credential exfil, LOLBIN abuse) that
  provenance-only systems don't attempt to classify at all. AuthGraph's
  Layer 1 "Hard Block" is a blunt instrument by comparison; it is not
  described as doing anything like BM25+BGE hybrid retrieval against a
  curated, MITRE-grounded corpus.
- `trajectory.py`'s cross-call session signals (accumulation, escalation,
  denial-echo, cross-minister pattern matching) — a genuinely different
  axis (behavioral pattern over a session window) than anything in §1.2,
  which are all single-call-focused provenance checks (even DRIFT's
  "Dynamic Validator... monitors deviations from the original plan" is
  closer to our COMPASS/escalation signal than to a full trajectory
  analysis, but this needs a direct read of DRIFT's mechanism to confirm,
  not assumed here).
- A cost profile that could plausibly run on commodity hardware — none of
  §1.2's systems report a CPU-only, no-frontier-API deployment story;
  this is a real, citable, different deployment point on the
  cost/guarantee curve, *if* Option B's numbers hold up at that cost.
- The exhaustive real-case classification (24 real AgentDojo tasks,
  literal/provenance/runtime-binding/exfiltration/neither breakdown) — no
  system in §1.2 or the survey reports an equivalent empirical breakdown
  of how real attacks distribute across their own constraint-type
  taxonomy.

**The uncomfortable version of the question, stated plainly:** if Kavach +
Option B ships with a `qwen2.5:7b`-powered, string-match-first provenance
check and reports (hypothetically) an 80-90% ASR reduction at a fraction
of AuthGraph's cost, that is a real, defensible, different point on the
cost/security curve. If it ships with a similar-cost, similar-guarantee
system that happens to also have a pattern-matching layer bolted on, that
reads as "AuthGraph, but worse, plus something unrelated" — and the
paper's reviewers would likely ask exactly that. **The differentiation is
not free; it has to be earned by the actual numbers**, specifically:
(a) Option B's ASR reduction at 7B-local-model cost vs. AuthGraph's at
GPT-4o cost, and (b) whether the 4-minister + Option B combination catches
attacks that provenance-only or pattern-only would each individually miss
(a genuine synergy claim, not yet measured).

### 2.4 What to borrow from the wider set (not just AuthGraph)

- **Fides's confidentiality/integrity labels** (arXiv:2505.23643) — even
  without adopting full IFC, a lightweight version (tag each stored
  observation with a coarse trust label — "from the source the user
  named" vs. "from elsewhere in the session") would strengthen our
  provenance store's schema beyond a flat text blob, and gives a cheap
  way to represent partial trust rather than a binary source_tools match.
- **NeuroTaint's semantic-transformation framing** (arXiv:2604.23374) —
  its core insight (taint must survive summarization/paraphrase, not just
  exact-copy) is directly relevant to our string-match-first design: a
  value that's been reformatted (different phone-number punctuation, a
  paraphrased address) will fail a naive string match. NeuroTaint's
  approach (semantic evidence + causal reasoning rather than exact
  string/pre-defined paths) is a real design pattern to borrow for the
  LLM-fallback half of our provenance check, beyond what AuthGraph itself
  specifies.
- **CaMeL's control/data separation** (arXiv:2503.18813) — probably too
  large an architectural commitment to adopt wholesale (it requires a
  custom interpreter and a two-LLM privileged/quarantined split), but the
  *principle* — untrusted data should never be able to influence which
  code path executes, only what data flows through an already-decided
  path — is a useful design lens for reviewing whatever extraction prompt
  Option B ends up using, to make sure injected content in a tool
  observation can't cause the *checker itself* to change its decision
  logic, only the values it's checking.
- **DRIFT's Injection Isolator** (arXiv:2506.12104, "masks instructions
  conflicting with the user query from the memory stream") — a
  potentially cheap addition on top of our raw-observation storage
  (§2.3 of `option_b_build_analysis.md`): if we're already storing raw
  observation text for provenance checking, a lightweight pass that flags
  (not necessarily removes) imperative-sentence patterns in that text
  before it re-enters the agent's context is a small, bolt-on extension
  worth scoping separately, not part of the core three constraint types.

---

## Part 3 — OpenClaw production reality (re-checked, materially different from the earlier finding)

**The earlier session's finding was: `before_tool_call`/`agent_end` hooks
were registered-but-never-invoked, tracked in issues #5513 and #5943, no
blocking hook available yet.** Re-checked directly against GitHub and
OpenClaw's own docs:

- **Issue #5943** ("Wire up before_tool_call plugin hook in tool execution
  pipeline") is now **Closed**. Fetches disagreed on whether it was closed
  via a merged fix or for another reason — this specific point could not
  be pinned down cleanly from what was retrievable here (one fetch showed
  no closing comment or PR link, a second showed no closure detail at
  all). **Do not cite a specific resolution mechanism for #5943 without a
  cleaner source** (e.g., a direct look at the issue's timeline via an
  authenticated GitHub session, not available in this environment).
- **Issue #5513** ("Plugin hooks... are never invoked") is **Closed as not
  planned**, with a linked-but-also-closed PR
  (`BingqingLyu/openclaw#13`). The maintainers explicitly declined to fix
  this particular reported bug — this does not necessarily mean hooks
  remain broken generally; it could mean this specific bug report was
  superseded by other work (consistent with #5943 being a more specific,
  separately-tracked, and apparently-resolved issue).
- **OpenClaw's official docs (`docs.openclaw.ai/plugins/hooks`) now
  describe `before_tool_call` as a fully specified, working hook**, with
  a documented event schema (`event.toolName`, `event.params`,
  `event.toolKind`, `event.derivedPaths`, `event.runId`,
  `event.toolCallId`, plus context fields) and a documented return
  contract (`{params?, block?, blockReason?, requireApproval?}`) with
  explicit decision semantics ("block: true is terminal"). **This reads
  as current, real, production documentation, not an aspirational
  roadmap page** — no experimental/beta caveat found.
- **Critically: there is a separate, also-documented `after_tool_call`
  hook** ("Observe tool results, errors, and duration") — this is exactly
  the tool-result-visibility gap `option_b_build_analysis.md` §2.3 scoped
  as needing new infrastructure for AgentDojo. If this hook is real and
  working as documented, **OpenClaw's actual production integration
  surface is better-shaped for provenance/runtime-binding than
  AgentDojo's** — structured `event.params` (no text-parsing needed) and
  a dedicated after-call observation hook (no reverse-engineering
  `messages` history needed), rather than worse-shaped as the earlier
  investigation assumed.

**Honest overall read:** the evidence assembled here (closed tracking
issues + current, unhedged documentation of a working, well-specified
hook pair) points toward **"provenance-in-production is very likely no
longer blocked,"** a meaningfully more optimistic finding than the earlier
session's "no blocking hook yet, post-hoc only." But this rests on
documentation and issue-tracker state, not a live integration test against
a running OpenClaw instance — **the next concrete step, before revising
any build plan on this basis, should be an actual smoke test**: install a
minimal plugin using `before_tool_call`/`after_tool_call` against a real
OpenClaw instance and confirm the hooks fire as documented. Until that
smoke test happens, treat "OpenClaw is unblocked" as a strong lead, not a
confirmed fact.

---

## Part 4 — Forward plan, sharpened

### 4.1 The strongest defensible version of Option B for Kavach specifically

Given §2.3's honest assessment, the version worth building is **not** "a
smaller AuthGraph" as a standalone claim. It's:

1. **Literal + provenance + AuthGraph-scoped runtime-binding**, built per
   `option_b_build_analysis.md`'s effort estimates (~5-7 days total),
   targeting the **OpenClaw hook pair** (§3) as the primary integration
   surface once smoke-tested, with AgentDojo kept as the benchmark/
   validation harness (not the production target).
2. **Explicitly measured as an addition to, not a replacement for, the
   4-minister layer** — the paper's real contribution claim should be
   about the *combination* catching cases neither layer catches alone,
   which requires a specific ablation: run (a) 4-minister only, (b)
   Option B only, (c) both together, against the same real-case set
   (the existing 24-case AgentDojo classification, extended if possible),
   and report whether (c) > max(a, b) on real attacks. **This ablation
   does not exist yet and is the single most important number missing
   from the current build.**
3. **A cost-disclosed number**, not just an ASR number: report Option B's
   ASR reduction *and* its actual latency/compute cost on the stated
   hardware (CPU-only laptop, `qwen2.5:7b`), directly next to AuthGraph's
   Table 3 numbers and their GPT-4o-tier cost. If Option B gets even 70%
   of AuthGraph's ASR reduction at a small fraction of the compute cost,
   that is a real, citable, different point on the curve. If it gets 30%
   of the reduction, the "lightweight" framing doesn't rescue the
   contribution and this needs to be said plainly, not spun.

### 4.2 The 2-3 things needed to make this a real contribution, not a follow-on

1. **The ablation in §4.1(2)** — quantitative evidence that layering
   provenance checking on top of pattern-matching genuinely outperforms
   either alone on real attacks, not just a design argument that it
   should.
2. **A real cost/ASR tradeoff curve**, not a single number — ideally
   showing where Option B sits relative to AuthGraph/CaMeL/Progent/DRIFT
   on the same axes (ASR, utility, utility-under-attack) at the actual
   measured cost. This requires running the constraint-extraction
   pipeline against the full AgentDojo suite (or a representative
   subset), not just the current 24-case InjecAgent-derived classification.
3. **Either the OpenClaw smoke test resolving positively (§3) and a real
   production-shaped deployment demo, or an honest acknowledgment that
   the production story is still AgentDojo-only** — claiming OpenClaw
   integration without the smoke test would be citing documentation as
   if it were a demonstrated result, which is exactly the kind of
   unverified claim this whole investigation has been trying to avoid.

### 4.3 Honest call: is Option B still the right investment?

**Yes, but reframed, not as originally scoped.** The crowded landscape
doesn't invalidate the problem (if anything, AuthGraph/CaMeL/Fides/DRIFT/
Progent all converging on the same problem in the same ~18 months is
strong evidence the problem is real and worth solving) — but it does
invalidate "build a provenance checker" as a *sufficient* contribution on
its own. Three independent teams have already published strong, validated
provenance mechanisms; a fourth implementation of the same idea, even a
cheaper one, is a weak paper contribution by itself.

**The defensible angle is the combination, quantitatively demonstrated**:
Kavach's actual novelty is having a real, already-deployed, corpus-grounded
technical-detection layer (the 4 ministers + trajectory.py's session
signals) that none of the provenance-only systems have, and the open,
unanswered, genuinely interesting question is whether *adding* a
lightweight provenance layer on top measurably outperforms either
approach alone, at a cost point none of the existing systems target
(CPU-only, no frontier-API dependency). That is a real, narrow, checkable
research question this codebase is uniquely positioned to answer — but
only if the ablation in §4.1(2) actually gets run and actually shows a
synergy effect. If it doesn't, the honest conclusion is that Kavach's
paper should lead with the 4-minister layer's own contributions (the
CHAN-102 provenance-correction work, the discriminability test as a
negative result motivating why pattern-matching alone is insufficient,
the STEWARD investigation as a documented dead-end with a clear causal
story) and treat Option B as validated-but-secondary future work rather
than force it into being the paper's central claim before the numbers
exist to support that framing.
