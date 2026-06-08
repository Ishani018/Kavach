# Kavach Paper Notes — June 3, 2026
## For §1 Introduction, §6 Related Work, §7 Limitations
## Written while research is fresh. Drop these into the paper when ready.

---

## Context that shapes the paper framing

On June 2, 2026 (Build 2026), Microsoft announced a deep partnership with
OpenClaw, including MXC (Microsoft Execution Containers) for OS-level agent
sandboxing, Scout (an OpenClaw-powered Microsoft 365 agent), and Agent 365
(Defender/Entra/Intune/Purview governance for agents). The tagline was
"Claws now work securely in the enterprise."

Separately, ClawGuard (arXiv:2604.11790, April 13, 2026, Singapore Management
University) was published — an OpenClaw-native deterministic tool-call
interceptor that achieves 0% ASR on AgentDojo under basic rules. This is the
closest prior art to Kavach and was missed in our original related work sweep.

Together these two developments STRENGTHEN the Kavach paper, not weaken it:
- Microsoft validated at Satya Nadella keynote level that OpenClaw enterprise
  security is urgent and real
- The semantic monitoring gap is explicitly unaddressed by Microsoft's stack
- ClawGuard's own paper says its residual failures need "system-level semantic
  monitoring" — which is exactly Kavach's contribution
- The three layers (MXC → ClawGuard → Kavach) are complementary, not competing

---

## §1 Introduction — positioning paragraph (ready to paste)

Concurrent with this work, Microsoft announced MXC (Microsoft Execution
Containers, Build 2026) — an OS-level policy sandbox for OpenClaw agents that
constrains filesystem, network, and UI access — alongside ClawGuard
[CITE:2604.11790], a deterministic rule-based tool-call interceptor that
achieves 0% attack success rate (ASR) on AgentDojo under explicit user-defined
rules. Kavach is complementary to both. MXC reduces blast radius but cannot
reason about agent intent: an agent authorized to read credential files and
make HTTP calls can be semantically manipulated into exfiltrating those
credentials via indirect prompt injection while remaining fully within its MXC
policy. ClawGuard's authors acknowledge this gap, noting that "content-misleading
attacks are inherently difficult to intercept without system-level semantic
monitoring" [CITE:2604.11790 §5]. Kavach occupies precisely this semantic layer:
embedding-based intent alignment, cross-session trajectory analysis, and
session-level enforcement without requiring pre-specified rules or OS integration.

---

## §6 Related Work — ClawGuard paragraph (ready to paste)

**ClawGuard** (arXiv:2604.11790) is the most closely related prior work.
It is OpenClaw-native and intercepts tool calls via four deterministic
components: a Content Sanitizer, Rule Evaluator, Skill Inspector, and
Approval Mechanism. Under basic rules on five LLMs, it achieves 0% ASR on
AgentDojo, ~5-14% ASR on SkillInject (from 26-48% baseline), and ~7-11%
ASR on MCPSafeBench (from 36-46% baseline). ClawGuard does not use semantic
embeddings — its detection is fully rule-based, requiring users to pre-specify
which tool patterns are permitted or forbidden. The authors explicitly
acknowledge a residual failure class: "content-misleading attacks, where the
model is convinced to misuse a permitted tool, are inherently difficult to
intercept without system-level semantic monitoring." Kavach addresses this
gap: rather than matching tool calls against user-defined rules, Kavach scores
the *semantic intent* of each call against a corpus of known attack patterns
using BGE embedding similarity, requires no per-deployment rule authoring,
and extends detection across session trajectories to catch multi-step attacks
that individually evade per-call rule systems.

**MXC / Microsoft Execution Containers** (Build 2026, Microsoft) provides
OS-level containment for OpenClaw agents — constraining filesystem paths,
network endpoints, and UI access via a JSON policy manifest enforced at the
kernel level. MXC is a blast-radius mechanism, not a semantic monitor: it
limits the *consequences* of a tool call but cannot determine whether an
authorized call was induced by injected content (the confused-deputy problem
[CITE:confused-deputy]). Microsoft's own MXC repository notes "no MXC profiles
should be treated as security boundaries currently." Kavach and MXC are
architecturally complementary: MXC constrains what an agent can touch, Kavach
monitors whether the agent's intent has been manipulated into misusing that
access.

---

## §6 Related Work — updated comparison table (for paper Table 1)

| System | Approach | ASR | Latency | OpenClaw-native | Session-aware | Semantic |
|---|---|---|---|---|---|---|
| ClawGuard [2604.11790] | Deterministic rules | 0% (AgentDojo, basic rules) | low | ✅ | ❌ | ❌ |
| AgentArmor [2508.01249] | Program analysis | 1.16-3% (AgentDojo) | 20.89s avg | ❌ | ❌ | ❌ |
| LlamaFirewall [2505.03574] | PromptGuard 2 + AlignmentCheck | 1.75% (AgentDojo) | 19ms (PG2 only) | ❌ | ❌ | partial |
| MELON [2502.05174] | Masked re-execution | 0.24-0.32% (AgentDojo) | 2× passes | ❌ | ❌ | ❌ |
| PromptArmor [2507.15219] | LLM guardrail | 0.00-0.56% (AgentDojo) | LLM pass | ❌ | ❌ | partial |
| OpenClaw PRISM [2603.11853] | Heuristic + local LLM scanner | recall 0.955 (own corpus) | ~15.8s p95 | ✅ | partial | ❌ |
| ZEDD [2601.12359] | Embedding drift | >93% acc | — | ❌ | ❌ | ✅ |
| MXC (Microsoft Build 2026) | OS containment | n/a (no injection defense) | kernel-level | ✅ | ❌ | ❌ |
| **Kavach (ours)** | BGE semantic + session trajectory | TBD (AgentDojo pending) | p95 <2s | ✅ | ✅ | ✅ |

Key differentiators Kavach can claim honestly:
- Only system that is BOTH OpenClaw-native AND semantic AND session-aware
- Sub-2s p95 latency vs PRISM's 15.8s and AgentArmor's 20.89s
- No pre-specified rules required (unlike ClawGuard)
- No lifecycle-wide instrumentation required (unlike PRISM's 10 hooks)
- No trained trajectory model required (unlike Trajectory Guard)

---

## §7 Limitations — additions needed (paste into existing §7)

**ClawGuard comparison.** ClawGuard achieves 0% ASR on AgentDojo under
explicit rules, which Kavach does not currently match. Kavach's contribution
is complementary — semantic/embedding-based detection without rule authoring —
but an honest evaluation should report both systems' numbers on the same
benchmark. We leave a direct head-to-head comparison to future work pending
completion of our AgentDojo evaluation.

**MXC integration.** Kavach is evaluated in OpenClaw embedded mode without
MXC. A defense-in-depth evaluation (Kavach inside an MXC sandbox) is left
for future work and would more accurately reflect the production deployment
scenario following the Microsoft + OpenClaw Build 2026 partnership.

**Mean-pooling chain leg.** Trajectory Guard (arXiv:2601.00516) demonstrates
that mean-pooling centroid approaches achieve F1 ≤ 0.69 on trajectory detection.
Our chain leg uses sequential pairwise cosines rather than a pure centroid
(partially addressing this), but a trained Siamese trajectory model [2601.00516]
would achieve higher F1. We propose this as future work.

---

## §8 Future Work — additions

- Replace the sequential-cosine chain leg with a lightweight Siamese trajectory
  model trained on Kavach's ledger data, addressing the Trajectory Guard F1
  ceiling.
- Evaluate Kavach inside an MXC sandbox (defense-in-depth with Microsoft's
  OS containment layer).
- Head-to-head comparison with ClawGuard on SkillInject and MCPSafeBench,
  the benchmarks where ClawGuard's deterministic approach leaves residual
  failures that semantic monitoring should address.
- Extend Kavach to OpenClaw's gateway mode (requires a gateway-level hook
  that does not currently exist — propose standardization of this primitive).

---

## Key citations to add (not in original related work)

- ClawGuard: arXiv:2604.11790 (Wei Zhao, Zhe Li, Peixin Zhang, Jun Sun — SMU)
- MXC: https://github.com/microsoft/mxc + Build 2026 Windows Developer Blog
- ACS (Agent Control Spec): https://commandline.microsoft.com/agent-control-specification-runtime-governance/
- SkillInject benchmark: used by ClawGuard, need to add to §4 (Evaluation Setup)
- MCPSafeBench: used by ClawGuard, need to add to §4

---

## One-line paper abstract suggestion (update when AgentDojo numbers are in)

"Kavach is an OpenClaw-native runtime security monitor that uses BGE embedding
similarity and session-level trajectory analysis to detect prompt injection
attacks at the tool-call boundary, achieving [X]% recall with [Y]% FPR at
[Z]ms p95 latency — without pre-specified rules, lifecycle-wide instrumentation,
or trained trajectory models."

Fill in X, Y, Z from Parv's Dell results.
