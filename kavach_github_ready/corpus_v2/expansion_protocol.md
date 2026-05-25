# Corpus v2 — Expansion Protocol

**Version:** 2.0  •  **Owner:** Janya + Pranitha  •  **Reviewer:** Jamieboy

---

## Why this document exists

The v1 corpus was written while we were staring at ClawHavoc and a handful of agent CVEs we'd already seen. The parliament passes those test cases at >90% recall. That number means nothing. We trained on the test set.

This document is the discipline that fixes that. The v2 corpus is written **blind** — sourced from MITRE ATT&CK technique IDs and OWASP Agentic 2026 categories, never from a CVE we've examined, never from a transcript we've debugged. The point is not to write more patterns. The point is to write patterns whose validity does not depend on what we already know.

If we follow this protocol and the parliament still hits ≥70% recall on InjecAgent (which we have never looked at), the system generalizes. If it doesn't, we have a real research finding: semantic embedding-based detection on a curated corpus has a ceiling, and the ceiling is what you get when you can't see the test cases.

---

## The rules

### Rule 1 — No CVE, no transcript

While writing v2 patterns, do not look at:

- The ClawHavoc transcript. At all.
- Any CVE database entry. We are writing from technique IDs, not from incidents.
- The InjecAgent test set. Not even the categories. Especially not the categories.
- AgentDojo cases. Same reason.
- Existing v1 corpus descriptions. Cover-the-page-with-your-hand.

You may look at:

- MITRE ATT&CK technique pages (tactic + technique description, not the example threat actors)
- OWASP Agentic 2026 category descriptions
- CWE entries (the abstract category, not specific instances)

### Rule 2 — Source-first, name-free

Every pattern must cite its source category, not its instantiation. Good source:

> source: MITRE ATT&CK T1552.001, OWASP Agentic 2026 A02

Bad source:

> source: ClawHavoc CVE-2026-21852

If you are writing a pattern *about* a known incident, stop. Write it about the technique class instead.

### Rule 3 — Three levels per pattern, in order

Each pattern has three description levels, and they MUST be written in this order:

1. **L1 (intent)** — What is the agent fundamentally trying to do? Written in plain English, no tool names, no syntax. Catches novel implementations of the same intent.

2. **L2 (mechanism)** — What general mechanism does the attack use? May reference categories of tools (e.g., "package manager", "shell"), but never specific commands or paths.

3. **L3 (surface)** — What does this look like at the API/syntax level? Concrete tool names, command flags, paths. This catches the specific instantiation.

The mistake in v1 was writing L3 first (because it was easiest), then writing L1 and L2 by paraphrasing L3 upward. That made L1/L2 secretly L3 in disguise. v2 writes top-down. If you cannot describe the intent without naming a tool, you have not understood the intent yet.

### Rule 4 — The "tomorrow" test

For every pattern, ask: *if an attacker invented a new tool tomorrow that achieves this same intent, would my L1 description catch it?*

If the answer is no, your L1 is too specific. Rewrite.

Example — a v1 pattern (bad):

```
L1: Agent uses curl to fetch a remote script and pipes it to bash
```

This catches `curl … | sh`. It does not catch `wget … | sh`, `Invoke-WebRequest | iex`, or a future tool we haven't seen. Rewrite:

```
L1: Agent retrieves content from a remote network location and immediately
    passes the retrieved bytes to a shell or interpreter for execution
```

Now the pattern is technique-defined, not tool-defined.

### Rule 5 — The "blue team" test

For every pattern, ask: *can a benign script trigger this?*

If yes, the pattern is too broad and will inflate FPR. The fix is usually to add a constraint about *what* is being executed, not *how*.

Example (bad — too broad):

```
L1: Agent invokes a shell command
```

Every legit code agent does this. Useless.

Example (corrected):

```
L1: Agent invokes a shell command whose contents originate from network
    bytes received during the same agent turn, with no user authorization
    of the specific bytes
```

Now the constraint is the provenance of the input, not the act of invocation. This is the correct shape.

### Rule 6 — No collaboration during writing

Each writer drafts their 25 patterns independently. After drafting, swap files with another writer for review.

The reviewer's job is to identify which patterns sound like the writer was looking at a specific known attack. Anyone whose patterns the reviewer can group by "these were clearly written about ClawHavoc" should rewrite those patterns.

### Rule 7 — One pattern, one intent

Do not write a pattern that captures two distinct intents. If your L1 has the word "and" connecting two verbs, split it into two patterns.

Bad:

```
L1: Agent reads credentials and sends them over a network connection
```

Two patterns:

```
PATTERN-A L1: Agent reads files containing authentication material
PATTERN-B L1: Agent transmits in-memory data to an external network destination
```

The combination is what gets you exfiltration; the parliament's job is to detect the combination at runtime, not to encode it as one pattern. Encoding combinations as patterns leaks training-set knowledge into the corpus.

### Rule 8 — Cite freshly

Every pattern's source field cites at most one MITRE technique ID, one OWASP category, and at most one CWE. If you find yourself citing four sources for one pattern, you are over-justifying — rewrite.

---

## Allocation

50 new patterns per minister × 4 ministers = **200 new patterns**, going from ~50 patterns per minister in v1 to ~100 per minister in v2.

| Minister | Writer | Source emphasis |
|---|---|---|
| EXECUTOR | Janya | MITRE T1059, T1190, T1195, T1546, T1574; OWASP Agentic A09 (supply chain), A05 (cascading hallucinations) |
| VAULT | Pranitha | MITRE T1552, T1078, T1539, T1555; OWASP Agentic A02 (excess agency), A06 (memory poisoning) |
| CHANNEL | Janya | MITRE T1041, T1567, T1071, T1048, T1572; OWASP Agentic A04 (orchestration manipulation) |
| NAVIGATOR | Pranitha | MITRE T1083, T1057, T1005, T1135, T1119; OWASP Agentic A01 (intent breaking & goal manipulation) |

Each writer covers 50 patterns total — 25 from their primary minister, then 8-9 each across the other three. Cross-coverage prevents per-writer style leaking into per-minister content.

---

## Quality gates before merge

A pattern is mergeable only when:

- [ ] All three levels written, in L1 → L2 → L3 order
- [ ] L1 has no tool name and no syntax
- [ ] L2 mentions at most a category of tools
- [ ] L3 is the only level allowed to name specific commands or paths
- [ ] Source field cites one MITRE technique + one OWASP/CWE
- [ ] Passes the "tomorrow" test (writer's self-check)
- [ ] Passes the "blue team" test (reviewer's check)
- [ ] Reviewer cannot identify the writer from style

---

## Validation after the corpus is loaded

After all 200 new patterns are added to `kavach_corpus_v1.json` (renamed v2 on merge):

1. Re-run `corpus_loader.py --rebuild` to rebuild the five collections.
2. Re-run the COMPASS calibration in the embedding lab. Threshold should land around 0.50 (per the research summary's expectations).
3. Run the 50 benign agent traces through the parliament. Target FPR < 5%. If above, prune the worst-offending patterns and re-validate.
4. Only after FPR < 5% on benign do we run InjecAgent. Running InjecAgent before benign FPR is calibrated produces meaningless precision numbers because we don't know how many of the "blocks" were the system being trigger-happy.

---

## What success looks like

The v2 corpus succeeds if, on InjecAgent (which the team has never looked at):

- BLOCK recall ≥ 70%
- BLOCK precision ≥ 80% (FPR on benign was already constrained to < 5% by gate 3)
- p95 latency < 200ms

If we hit all three on a corpus written from MITRE/OWASP without seeing the test set, that is a publishable result. The framing for the paper is exactly this protocol: "we wrote the corpus from technique taxonomies, then ran a held-out benchmark, and these are the cold-recall numbers."

If we miss any of the three, that is also publishable — as a finding about the ceiling of curated-corpus semantic detection. Either way, the protocol generates an honest result. The only failure mode is testing on the training set, and this document exists to prevent that.
