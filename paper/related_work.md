# Related Work — Differentiation Paragraphs
# Updated: May 2026 — post-research-sweep additions marked ✦ NEW

One paragraph per cited system. Each paragraph: what the system does, what it
overlaps with Kavach, and **what specifically differentiates Kavach**. The
differentiation must be a substantive architectural or methodological
difference, not just "we have higher numbers."

These map directly to §6 of `paper/skeleton.tex`.

---

## LlamaFirewall (Chennabasappa et al., arXiv:2505.03574, Meta / PurpleLlama)

LlamaFirewall is Meta's production-deployed three-layer guardrail: PromptGuard 2
(fine-tuned DeBERTa, 86M and 22M parameter variants) detects jailbreaks at
input time with reported recall of 97.5% at 1% FPR on English and 88.7%
on multilingual benchmarks at 19.3 ms on A100 GPUs. AlignmentCheck audits
agent chain-of-thought for goal divergence using Llama 4 Maverick or Llama 3.3
70B, reducing AgentDojo ASR from a 17.6% baseline to 2.89% standalone and to
a combined 1.75% with PromptGuard 2 (utility 42.7%). CodeShield applies Semgrep
rules and regex across eight programming languages at 96% precision, 79%
recall on insecure-code labels from CyberSecEval3.

**Differentiation.** LlamaFirewall is a *spatial* defense — three independent
rails fire in parallel at two enforcement points (input-time and output-time).
AlignmentCheck operates on the agent's reasoning trace, not on resolved tool
calls with actual arguments. No component in LlamaFirewall fires at the
tool-call boundary before the tool executes; Kavach does. Furthermore,
LlamaFirewall's PromptGuard 2 and CodeShield operate on text classification and
static analysis respectively — neither uses a curated attack-pattern corpus
against which the semantic content of a tool call is compared. Finally, Kavach
addresses the *temporal* dimension that LlamaFirewall does not: the parliament
is registered before any user-installable extension can run a tool call,
ensuring temporal authority as formalized in §4.

---

## AgentSpec (Wang, Poskitt, Sun; arXiv:2503.18666, last revised Jul 2025)

AgentSpec is a lightweight rule DSL where each rule is
`trigger + predicate + enforcement`. The paper reports >90% prevention on code
agents and 100% on embodied tasks. Rules are hand-written per deployment,
interpretable, and auditable.

**Differentiation.** AgentSpec rules are written by hand for each deployment;
Kavach's ministers semantically match against a corpus of attack-pattern
*descriptions* via embedding similarity, which generalizes to attacks that
don't exactly match a hand-written rule. The two are complementary: an
AgentSpec rule layer above the parliament catches deployment-specific policies
(e.g., "this agent should never write outside `/workspace`") while the
parliament catches the semantic tail of known attack categories. The
rule-DSL approach also cannot detect novel attacks whose surface syntax has
not yet been enumerated; Kavach's corpus-based approach propagates
generalization through the embedding space.

---

## AGrail (Luo, Dai, Liu, Banerjee, Sun, Chen, Xiao; arXiv:2502.11448, ACL 2025)

AGrail is a "lifelong guardrail" with adaptive safety-check generation, test-time
adaptation via two cooperative LLMs (Claude-3.5-Sonnet / GPT-4o), and a memory
module that grows over deployment. Reported 0% ASR on AdvWeb; 3.8% ASR (env
risk) and 5% (system sabotage) on Safe-OS; and ~17% averaged on EIA across
action-generation and grounding tasks.

**Differentiation.** AGrail's adaptation loop generates new safety checks at
runtime via LLM cooperation — powerful but expensive (two full LLM round-trips
per check) and the safety-check generation itself is an attack surface. Kavach's
adaptation is limited to corpus growth (Detective-style memory promotion in
future work) and does not run an LLM in the hot path of the verdict — only
embedding lookups against a persistent ChromaDB store. The latency profile is
consequently very different: Kavach targets <200 ms p95 at the tool-call
boundary; AGrail's two-LLM cooperative loop incurs two LLM RTTs per check.

---

## ShieldAgent (Chen, Kang, Li; arXiv:2503.22738)

ShieldAgent extracts verifiable rules from policy documents into action-based
probabilistic rule circuits. Reports "SOTA on ShieldAgent-Bench and three
existing benchmarks, outperforming prior methods by 11.3% on average with a high
recall of 90.1%." Claims 64.7% reduction in API queries and 58.2% reduction in
inference time vs LLM-judge baselines.

**Differentiation.** ShieldAgent's rule circuits are derived from
natural-language policy documents — a strong fit for compliance-driven
deployments where the policy text already exists. Kavach's corpus is derived
from MITRE ATT&CK technique IDs and OWASP Agentic 2026 categories — a strong
fit for security-driven deployments where the threat model is the input. The
two are complementary. Additionally, Kavach's asymmetric verdict combination
(any minister BLOCK suffices to block) differs from ShieldAgent's probabilistic
circuit combination, which averages across circuits.

---

## CaMeL (Debenedetti et al., Google DeepMind; arXiv:2503.18813, v2 Jun 2025)

CaMeL applies information-flow control via a dual-LLM architecture (Privileged
Model + Quarantined Model), a custom Python interpreter with per-value capability
metadata, and a deterministic policy engine gating tool calls. Reports "solves
77% of tasks with provable security" on AgentDojo. An extension,
"Operationalizing CaMeL" (Tallam & Miller, arXiv:2505.22852), proposes
tiered-risk access and a formally verified interpreter layer.

**Differentiation.** CaMeL is a *static* defense: it constrains what an agent
can do based on the capability lattice at registration time. It does not read
the semantic content of a tool call's arguments. Kavach is a *semantic* defense:
it embeds the actual argument content and asks whether it resembles a known attack
class. CaMeL's strength is provability; Kavach's strength is generalization to
attacks that don't trip a capability constraint. The two cover orthogonal failure
modes.

---

## FIDES ✦ CORRECTED (Costa, Köpf, et al., Microsoft Research; arXiv:2505.23643, v2 Sept 2025)

> ⚠ Previous entries labelled FIDES "federated detection." This is **incorrect**.
> FIDES is *information-flow control*, not federated detection.

FIDES propagates confidentiality and integrity labels through messages, actions,
tool calls, and tool results in multi-agent systems. Introduces novel IFC
primitives for selective information hiding.

**Differentiation.** FIDES operates at the *information-flow* layer — tracking
where data came from and what it may be used for. Kavach operates at the
*semantic-pattern* layer — detecting whether an action resembles a known attack
class regardless of data provenance. The two are complementary: FIDES for
provenance-based taint tracking; Kavach for semantic attack-pattern matching.

---

## RTBAS (Zhong, Chen, Wang, McCall, Titzer, Miller, Gibbons; arXiv:2502.08966, CMU + Two Sigma)

RTBAS adapts IFC to LLM agents via two "dependency screeners": LM-as-judge and
attention-based saliency. Reports "prevents all targeted attacks with only a 2%
loss of task utility when under attack" on AgentDojo.

**Differentiation.** RTBAS's risk score is aggregate; Kavach decomposes the
decision into four independent minister verdicts plus COMPASS, yielding
interpretable BLOCK reasons with matched pattern IDs. Kavach's deny-first
asymmetric combination is more conservative; RTBAS's saliency screener has a
similar cost profile to Kavach's embedding-only approach.

---

## Conseca (Tsai & Bagdasarian, Google; arXiv:2501.17070, HOTOS '25)

Conseca generates just-in-time contextual policies via an isolated policy LLM
that sees only trusted context. Reports ~60% completion with Conseca on benign
tasks.

**Differentiation.** Conseca's policy LLM generates policies from the current
context; Kavach's corpus is offline and stable. The two address different failure
modes: Conseca catches context-specific novel policies; Kavach catches known
attack-class patterns.

---

## Task Shield (Jia, Wu, Qin, Squicciarini; arXiv:2412.16682, ACL 2025)

Task Shield reframes defense as task-alignment: each intermediate instruction
must demonstrably advance the user's task. Reduces AgentDojo targeted ASR from
~45% baseline to ~22%.

**Differentiation.** Task Shield evaluates "is this on-task?"; Kavach's COMPASS
does the same via cosine similarity to seeded intent. Kavach extends with four
attack-category ministers: "the agent is on-task but the action is `/etc/shadow`"
is caught by VAULT even though COMPASS allows it.

---

## Trajectory Guard (Advani; arXiv:2601.00516, AAAI 2026)

Siamese Recurrent Autoencoder with hybrid contrastive + reconstruction loss for
real-time trajectory anomaly detection.

**Differentiation.** Trajectory Guard's sequence-aware autoencoder outperforms
Kavach's single-vector COMPASS cosine on pure drift detection — acknowledged in
§7. Where Kavach contributes beyond Trajectory Guard: drift is one of four
signals; the speaker's deny-first combination treats COMPASS drift as
corroborating evidence, not the verdict. Trajectory Guard requires trajectory
data for training; Kavach's COMPASS requires only the user's intent string.

---

## TaskTracker (Abdelnabi, Fay, Cherubin, Salem, Fritz, Paverd; arXiv:2406.00799, v6 Mar 2025)

Activation-delta probes: linear classifiers on LLM internal-activation differences
before/after external data injection. White-box. 500K-instance toolkit across
6 SoTA LMs.

**Differentiation.** TaskTracker requires white-box model access; Kavach's COMPASS
works on text embeddings only and runs against any agent. CORTEX (future work §8)
is essentially TaskTracker as a fifth Kavach minister.

---

## DeepContext ✦ NEW (Albrethsen, Datta, Kumar, Rajasekar; arXiv:2602.16935, Feb 2026)

Stateful real-time guardrail: fine-tuned turn-level embedding model fed into a
lightweight RNN. F1 0.84 on multi-turn jailbreak detection, sub-20 ms on T4 GPU.
Explicitly proposes "intent distance between user intent and agent actions" — a
cosine-based alignment oracle conceptually identical to Kavach's COMPASS.

**Differentiation.** DeepContext is a *single* embedding-RNN classifier focused
on user-turn drift; Kavach's COMPASS measures cosine distance between seeded
user intent and each proposed *agent action*, and feeds a four-minister parliament.
DeepContext has no attack-pattern corpus; Kavach's ministers match against curated
MITRE/OWASP-sourced descriptions, making decisions interpretable (matched pattern
ID named in BLOCK reason). DeepContext's sequence modelling is stronger for
multi-turn behavioral drift; Kavach's corpus matching is stronger for single-turn
tool-call semantic classification.

---

## PSG-Agent ✦ NEW (arXiv:2509.23614)

PSG-Agent ("Personality-aware Safety Guardrail") introduces four components: Plan
Monitor, Tool Firewall, Response Guard, Memory Guardian — with cross-turn risk
accumulation. Outperforms LlamaGuard3 and AGrail. Personalized to user traits.

**Differentiation.** PSG-Agent's four components are superficially similar to
Kavach's four ministers but differ in three critical ways. (1) PSG-Agent is
*personalized* to user personality; Kavach applies a universal attack-pattern
corpus, making it deployment-stable and auditable. (2) PSG-Agent collapses oracle
and detector into a single pipeline; Kavach separates the COMPASS alignment oracle
from four pattern-matching ministers, allowing independent signals combined
asymmetrically. (3) Kavach fires at the tool-call boundary before execution;
PSG-Agent's execution timing is not made explicit.

---

## OpenClaw PRISM ✦ NEW (arXiv:2603.11853)

"Zero-Fork, Defense-in-Depth Runtime Security Layer for Tool-Augmented LLM
Agents" — middleware on the same OpenClaw runtime as Kavach.

**Differentiation.** PRISM adds sequential security checkpoints along the request
path without forking. Kavach differs: (1) uses a semantic corpus of 200
attack-pattern descriptions across four specialist ministers — PRISM does not use
a domain-specific corpus; (2) asymmetric verdict combination (any minister BLOCK
vetoes) is stronger than sequential checkpoint passing; (3) Kavach documents the
production gateway-path hook gap (issues #5513 and #5943, since resolved upstream
in v2026.4.15) that determines whether `before_tool_call` fires at all — without
a working pre-execution hook, neither PRISM nor Kavach achieves true
pre-execution interception.

> The team must read arXiv:2603.11853 in full before submission to confirm
> this differentiation. If PRISM also ships upstream hook fixes, update accordingly.

---

## DRIFT ✦ NEW (SaFo-Lab; arXiv:2506.12104)

Dynamic Rule-Based Defense with Injection Isolation: Secure Planner + Dynamic
Validator + Injection Isolator. Evaluated on AgentDojo, ASB, AgentDyn.

**Differentiation.** DRIFT operates at plan-time, not tool-call-time. It uses
rules; Kavach uses corpus-based embedding similarity. The two are complementary:
DRIFT catches plan-level injections; Kavach catches resolved tool-call semantic
patterns that slipped past plan-level inspection.

---

## ShieldNet ✦ NEW (arXiv:2604.04426, Apr 2026)

Network-level guardrail for MCP supply-chain attacks. SC-Inject-Bench:
10,000+ malicious MCP tool descriptions, 25+ MITRE ATT&CK derived attack types.
F1 0.995, 0.8% FPR.

**Differentiation.** ShieldNet and Kavach share corpus-design philosophy (MITRE
ATT&CK derived, curated descriptions) but operate at different layers. ShieldNet
is a *network* guardrail intercepting MCP protocol traffic via proxy; Kavach is
an *agent-runtime* guardrail intercepting the agent's resolved tool calls with
actual runtime arguments. Complementary: ShieldNet guards the supply-chain
registration of tools; Kavach guards the invocation of those tools with
attacker-influenced arguments.

> ShieldNet's SC-Inject-Bench is worth running Kavach's ministers against as a
> supplementary benchmark. Add to Workstream D.

---

## BARRED ✦ NEW (arXiv:2604.25203, Apr 2026)

Synthetic training of custom policy guardrails via asymmetric debate: two agents
debate with structurally different roles (direct-violation vs intent-reversal).

**Differentiation.** BARRED's "asymmetric" refers to debate *roles* during
synthetic data generation. Kavach's "asymmetric verdict combination" is an
*inference-time* property: any single minister returning BLOCK vetoes the call.
The two uses of "asymmetric" are orthogonal; Kavach's paper must define its own
term precisely (see §4 formal definition) to avoid confusion.

---

## TraceSafe-Bench ✦ NEW (arXiv:2604.07223, 2026)

Benchmark (not a defense) for evaluating guardrails on multi-step tool-call
trajectories. Uses BFCL multi-step traces with localized adversarial mutations.

**Relevance.** Kavach should be evaluated against TraceSafe-Bench in Workstream D
alongside InjecAgent. Its multi-step trajectory evaluation tests whether a
guardrail detects attacks distributed across multiple tool calls — more stringent
than InjecAgent's single-injection cases.

---

## SoK: Trust-Authorization Mismatch ✦ NEW (arXiv:2512.06914)

Coins "Trustworthiness-Authorization Mismatch" — static authorization decouples
from runtime trustworthiness.

**Relevance (not a defense).** Strong motivational citation for §2 and §4.
Directly supports the necessity claim in Theorem~\ref{thm:coverage}: even a
correctly authorized agent can be manipulated at runtime — the gap the
temporal-defense-in-depth axis fills.

---

## Commercial baseline reference: DKnownAI Guard (arXiv:2604.24826, Apr 2026)

Published head-to-head benchmark of AWS Bedrock Guardrails, Azure Content Safety,
Lakera Guard, and DKnownAI Guard on AI-agent security risks with human-annotation
ground truth. DKnownAI Guard: 96.5% recall, 90.4% TNR. Use this as the
commercial-baseline comparison row in the evaluation table rather than vendor
blogs.

---

## The DeepContext / TaskTracker / COMPASS triangle

All three address intent-action alignment or task-drift detection. Recommend one
unified paragraph in §6:

- **TaskTracker** (activation-deltas, white-box, 2024) — requires model internals;
  strongest for subtle value-loading attacks.
- **DeepContext** (RNN over turn embeddings, Feb 2026) — sequence-aware, black-box
  compatible, 20 ms; focused on *user-turn* drift.
- **COMPASS** (cosine between seeded user intent and proposed agent action, Kavach)
  — session-stateful, black-box, instantaneous; explicitly compares *agent action*
  against *user intent*, not user turn against user turn.

Key COMPASS novelty: *asymmetric seeding model* — intent embedded once at session
start becomes a fixed reference; every subsequent agent action compared against it.
DeepContext computes drift relative to the evolving user-turn sequence; COMPASS
computes drift relative to the initial declared intent. Complementary threat models.
