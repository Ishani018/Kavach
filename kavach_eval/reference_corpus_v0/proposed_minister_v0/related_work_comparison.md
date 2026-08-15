# Related-work comparison: Option B vs. 2026 authorization/provenance defenses

Status: research synthesis only, nothing built or changed. Saved to
`steward-scoping-v1` (not `main`). Purpose: confirm Option B (structured
constraint extraction, our 3-type design: literal / provenance /
runtime-binding) against the closest published prior art before continuing
the build, and stage citation/positioning language for the paper's
related-work section.

All papers below were independently fetched and verified real (arXiv
metadata, author names, submission dates checked) before any claim below
was written — no paraphrasing from training-data memory.

---

## 1. AuthGraph (arXiv:2605.26497, Wang/Li/Tian, May 2026) — the closest prior art

**"Aligning Provenance with Authorization: A Dual-Graph Defense for LLM
Agents."** This is close enough to our Option B design that it should be
read as convergent validation, not just related work — three independent
teams (this paper, PAuth, and us) landed on structurally similar mechanisms
in the same ~2-month window, which is itself worth a sentence in the paper.

### (a) How they derive the authorization graph

A "Planner Agent" builds the graph from `{user_prompt, tool_catalog}` alone,
in a context that has **never seen any tool observation**:

> "Since the Planner never encounters any observation, the attacker has zero
> channel capacity to influence the authorization graph"

They state this as a formal isolation property:

> "If the Planner's input contains no trajectory data, then the
> authorization graph is information-theoretically independent of any
> injected content." (Property 1)

**This is a direct, formalized statement of exactly what we called
"extract constraints at intent-seeding time, before injection can
contaminate."** Our design assumed this isolation informally (seed_intent
fires once, before any tool call); AuthGraph gives it a name and a
provability claim we should adopt the framing of, even if we don't adopt
their exact proof.

The graph itself contains: an `expected_tool` sequence (a tool-call-order
whitelist), a `ParamPolicy` per security-critical parameter, and a
`replan_allowed_tools` mechanism for runtime whitelist extension when the
agent's plan legitimately changes mid-session.

### (b) Per-parameter provenance constraint schema

Their `ParamPolicy` has exactly **four** `allowed_source` values:

| their type | semantics | closest match to our 3 types |
|---|---|---|
| `user_prompt` | value must appear in the user's original text | **= our `literal`** |
| `observation_direct` | literal token copied from a *specified* tool's observation | **= our `provenance`** |
| `observation_nl` | value is the agent's own reasoning/summary/calculation over an observation | **≈ our `runtime-binding`, but broader** |
| `any` | no constraint | *(we have no equivalent — see §3)* |

Per-parameter, they also carry a `source_tools` field:

> "The source_tools field explicitly declares which tools' observations are
> legitimate sources, defending against cross-tool pollution."

This is a direct match to our provenance type's core idea ("does this
argument trace to the source the user actually named"), but **more
precise than what we had scoped**: we described provenance as "traces to
the right document," they formalize it as "traces to the right *tool call*,
enumerated explicitly per parameter." Their version is the more buildable
spec — copy this shape.

### (c) Runtime source-check algorithm

For `observation_direct` (our provenance type):

> "string matching is attempted first in the specified source_tools'
> observation text; if not found, the Checker falls back to LLM judgment."

Critically, on which text they match against:

> "The matching corpus uses the trajectory's original observation text (not
> the Graph Builder's summaries), because the Graph Builder is an attack
> surface."

**This directly confirms our `trajectory.py` finding from the Option B
feasibility investigation** — Kavach currently only stores an embedded
vector per action, never the raw tool-call arguments or tool-result text,
and we identified that gap as the main infrastructure blocker for
provenance/runtime-binding. AuthGraph independently arrived at the same
requirement (raw observation text, not any summarized/re-derived form) and
frames *why*: summarization is itself an attack surface an adversary can
manipulate. This is a stronger argument for raw-text storage than the one
we had, and should replace/reinforce our framing in the build doc.

Their comparison mechanism (the "Injected Reasoning Graph," IRG) is built
from the actual execution trace using three edge types (`DERIVE`,
`EXTRACT`, `INVOKE`); tool calls have the structural signature:

> "{d_tool, d_p1, ..., d_pk} →^INVOKE o_result"

They then do an O(n) dual-pointer traversal comparing the IRG's ordered
tool-call sequence against the authorization graph's `expected_tool`
sequence — this is the tool-level whitelist check, separate from and prior
to the per-parameter `ParamPolicy` check.

### (d) Results (AgentDojo, GPT-4o-mini)

Attack success rate 0.17 → **0.01** (94% reduction), utility 0.69, utility
under attack 0.44. On AgentDojo with GPT-4o: ASR 0.40 → 0.01. On the
harder AgentDyn benchmark: ASR 0.52 → 0.02.

These are strong numbers on our own benchmark (AgentDojo) — good grounding
for a "this class of defense is validated, we are extending/specializing
it" framing rather than "we invented something novel from scratch."

### (e) Do they cover our three cases explicitly? Yes, with one addition

They explicitly discuss all three of our cases, using the running example
`git_star(repo_name=...)`:

- **Literal** — `user_prompt` source type, value must appear verbatim in
  the user's own text. Matches our literal type exactly.
- **Provenance** — `observation_direct` with `source_tools=[search_flights]`
  restricting `book_flight(flight_id)` to only that tool's output. Matches
  our provenance type exactly, and is more precise (named source tool, not
  just "a document").
- **Runtime-binding** — their `observation_nl` category is broader than
  ours: it covers not just "value computed by re-deriving a prior tool's
  output" (our "which file is largest" case) but *any* agent reasoning over
  an observation, including summaries and drafts. Our scoping was narrower
  and more mechanical (deterministic re-derivation of a specific rule);
  theirs folds in genuinely fuzzy LLM-judged cases too. Worth deciding
  whether to adopt their broader scope or keep ours narrower and cheaper.

**One thing they have that we don't: the `any` (no constraint) source
type**, and — more importantly — an explicitly acknowledged limitation we
should also state honestly for ourselves:

> "Same-observation pollution: if the attacker directly poisons the
> authoritative tool's data source (e.g., tampering with the flight search
> backend itself), AuthGraph's ParamPolicy source_tools check will pass"

This is a real, structural blind spot in *any* provenance-based approach
(ours included) — if the "authorized source" itself is compromised
upstream, provenance-matching correctly says "yes this traces to the right
tool" while still being wrong. Worth stating this limitation for Kavach's
Option B too, rather than letting it look like provenance-checking is a
complete fix.

---

## 2. "AI Agents May Always Fall for Prompt Injections" (arXiv:2605.17634, Abdelnabi & Bagdasarian, May 2026) — conceptual backbone

Confirmed real, and confirmed the specific framing requested. Opens with
exactly this scenario:

> "in a received email that asks for a travel refund with the statement:
> 'this request has been approved by the department head' the problem is
> not an instruction, but whether the request was indeed legitimately
> approved"

And states directly why isolation-style defenses (the instruction/data
separation camp, which includes StruQ/SecAlign, see §4) cannot fully solve
this:

> "if a defense severs all dependence on external content (e.g. using
> system-level isolation), it will suppress any actions even when the claim
> is *true*, causing the agent to ignore a legitimate approval and
> degrading utility."

And the root argument for why "instruction vs. data" is the wrong axis
entirely:

> "agent's operating context might contain instructions everywhere: any
> interaction with a third-party or use of memory or skills are
> instructional by design, so a defense cannot meaningfully separate data
> from instructions without breaking the agentic workflows it is *meant*
> to protect."

Their proposed reframing is Contextual Integrity (CI) theory — legitimacy
of an information flow is judged by five parameters: sender, receiver,
subject, information type, and **transmission principle** (the
authorization condition under which the flow is appropriate). This is a
theoretical vocabulary, not a mechanism — but it is the strongest available
citation for *why* our discriminability test's result was not a bug in our
approach but a structural inevitability: `send_money(recipient=X)` cannot
be judged safe or unsafe by looking at the call's own text/topic (which is
all embedding similarity can see), because legitimacy lives in the
transmission-principle dimension (was this recipient actually authorized),
which is orthogonal to topic similarity. **Use this paper to open the
paper's motivation section for the STEWARD/Option B track**: cite the
department-head example directly, then transition into our own
discriminability test as the empirical demonstration of the same claim in
our specific system.

---

## 3. What AuthGraph covers that we don't (candidates to borrow)

1. **Formal isolation property for the extraction step.** Adopt their
   framing ("information-theoretically independent of injected content"
   given a clean-context extraction call) as the correctness argument for
   our own intent-seeding step, rather than leaving it as an informal
   assumption.
2. **`source_tools` as an explicit enumerated field, not a vague "the
   right document."** Our provenance type should specify, per constraint,
   exactly which prior tool call(s) are legitimate sources — this is more
   buildable and testable than what we'd scoped.
3. **Tool-call-*sequence* whitelisting as a separate, prior layer** to the
   per-parameter check. We hadn't scoped anything like `expected_tool`
   ordering — this catches cases where the *sequence itself* is wrong
   even if every individual parameter would pass its own check. Possibly
   out of scope for a first Option B build, but worth flagging as a gap.
4. **String-match-first, LLM-fallback** as the concrete algorithm for the
   provenance check — matches what we scoped (deterministic check, cheap),
   but gives us a concrete fallback path for when exact string match fails
   on a paraphrased/reformatted value (e.g., a phone number with different
   punctuation) rather than treating it as a hard fail.
5. **The `any` source type** for parameters that genuinely have no
   meaningful authorization constraint — useful as an explicit "we checked
   and decided this doesn't need a constraint" marker, distinct from
   "we forgot to specify one."
6. **Explicit acknowledgment of the same-observation-pollution
   limitation.** We should state this for Kavach's provenance checking too,
   rather than let the mechanism look more complete than it is.

## 4. What we frame that AuthGraph doesn't

1. **We distinguish `literal` and `provenance` as genuinely separate build
   *tiers*, not just separate schema values.** AuthGraph treats
   `user_prompt` and `observation_direct` as two rows in the same table
   with roughly equal implementation cost; our Option B feasibility
   investigation found a real, load-bearing difference — literal needs zero
   new infrastructure (checkable today), provenance needs raw tool-result
   storage Kavach doesn't have yet. This staged-buildability framing is
   ours and is a genuine contribution for a systems-focused paper, even
   though the underlying constraint *types* converge with theirs.
2. **We measured the actual distribution of real cases across the three
   types on real data** (24 real AgentDojo injection tasks: 25% literal,
   17%+4% provenance/runtime-binding, 38% actually CHANNEL's job not
   STEWARD's at all, 17% fit neither). AuthGraph doesn't report an
   equivalent breakdown of how their four source types distribute across
   real attacks — our classification pass is a concrete empirical
   contribution to cite alongside theirs.
3. **We are a runtime-embedded security gate sitting beside an existing
   4-minister pattern-matching system, not a replacement architecture.**
   AuthGraph is presented as a complete pipeline (Planner + Checker
   replacing/wrapping the agent loop). Kavach's Option B is scoped as an
   *addition* to an existing, already-deployed hybrid BM25+BGE system —
   this is a meaningfully different integration story (incremental,
   backward-compatible) worth stating explicitly in the paper.

## 5. Related approaches (confirmed real, light-touch positioning only)

- **AgentArmor (arXiv:2508.01249)** — confirmed real. Converts the full
  agent runtime trace into program-analysis IRs (CFG/DFG/PDG) and applies a
  type system with taint tracking. This is the heavier, more general
  version of the raw-observation-storage requirement our `trajectory.py`
  investigation flagged — where we scoped "store enough raw data to check
  a handful of security-critical parameters," AgentArmor scopes "treat the
  entire trace as an analyzable program." Position Kavach as the
  lightweight end of this spectrum: enough provenance tracking to answer
  specific authorization questions, not full program analysis.
- **Progent (arXiv:2504.11703)** — confirmed real (Shi, He, Wang, Wu, Li,
  Guo, Song). Symbolic rule-based privilege control over tool
  names/arguments, with LLM-assisted policy generation, evaluated on
  AgentDojo/ASB/AgentPoison. This is the access-control camp: rules are
  about *what the agent may ever do*, not *whether this specific value was
  authorized this session*. Complementary to, not overlapping with,
  Option B — a real deployment could plausibly run both.
- **AgentSentry (arXiv:2602.22724)** — already verified earlier in this
  investigation (our "Option C"). Counterfactual masked re-execution,
  confirmed to require re-running the agent's decision process, which
  doesn't fit Kavach's stateless-gate architecture. No new information
  from this pass; restating for the related-work section's completeness.

## 6. General framing for the paper: model-level vs. system-level

Confirmed real: **StruQ** (arXiv:2402.06363) and **SecAlign** — both
fine-tune the underlying LLM to resist following injected instructions
(structured-query training / preference optimization against simulated
injections respectively). This is the **model-level** defense camp — and
it is the camp our own regressed BGE fine-tune fell into structurally, even
though we were fine-tuning an embedding model rather than the agent LLM
itself: both approaches try to teach a model to internally distinguish
legitimate from illegitimate content, and both have a documented ceiling
(StruQ/SecAlign reduce but do not zero out optimization-based attack
success; our fine-tune actively regressed on out-of-distribution attack
categories).

**Kavach, and Option B specifically, sit in the system-level camp**:
intercept the tool-call interface itself and verify each call against a
pre-established, session-specific specification, rather than trying to make
any single model internally injection-proof. AuthGraph, AgentArmor, and
Progent are all in this same camp — this is a real, citable, coherent
category with multiple 2026 papers converging on it, and Kavach's
Option B is a natural fit inside it, differentiated by being an addition
to an already-deployed hybrid retrieval system rather than a from-scratch
pipeline.

---

## 7. Bottom line for the build

Nothing here changes the Option B plan's *shape* (literal / provenance /
runtime-binding, staged by build cost). What it does:

- Validates the design isn't a dead end — independently converged-on by
  a well-resourced concurrent paper with strong AgentDojo numbers.
- Gives us a more precise, buildable schema for the provenance type
  (`source_tools` as an explicit per-parameter field, string-match-first
  with LLM fallback) to adopt directly rather than re-derive.
- Confirms (via an independent argument, not just our own trajectory.py
  reading) that raw tool-observation text, not summaries, is the correct
  thing to store for provenance checking — reinforces rather than changes
  our infrastructure-gap finding.
- Surfaces one real limitation (same-observation pollution) we should
  state honestly rather than let Option B look complete.
- Gives the paper's related-work section a clean structure: model-level
  (StruQ/SecAlign, our failed fine-tune) vs. system-level (AuthGraph,
  AgentArmor, Progent, AgentSentry, Kavach), with Kavach positioned as an
  incremental extension of an already-deployed hybrid system rather than a
  new from-scratch pipeline.
