# Reference Corpus v0 — Exploratory, Standalone (NOT integrated)

Built 2026-07-07T20:44:44.965737. **Not used by the live
parliament. `kavach_corpus_v1.json` / `kavach_corpus_v1_ORIGINAL.json` were only
READ (to build the technique cross-reference) — never written.**

## Sigma (SigmaHQ/sigma, populated falsepositives only)

- Total rule files scanned: **3140**
- Parse errors: 3
- No `falsepositives` field at all: 22
- `falsepositives` present but only `["Unknown"]`/empty: 1292
- **Usable (populated, non-Unknown falsepositives): 1823**
- Of those, map to a MITRE technique our corpus already has a pattern for: **729**

## LOLBAS (LOLBAS-Project/LOLBAS)

- Binary yml files scanned: **242**
- Parse errors: 0
- Total individual abuse-command entries extracted: **480**
- Binaries with at least one command mapping to a technique our corpus already
  has a pattern for: **81**

## Files written

- `sigma_falsepositives.json` — 1823 entries: title, tags, mitre_techniques,
  detection_summary (raw YAML dump of the detection block), falsepositives list,
  matched_kavach_techniques / matched_kavach_patterns.
- `lolbas_dualuse.json` — 242 entries: binary_name,
  legitimate_use_description (the binary's own stated purpose — LOLBAS has no
  separate "legit use" field per-command, so this is the binary-level
  Description), abuse_commands (list of {command, abuse_description, usecase,
  category, mitre_technique}), matched_kavach_techniques / matched_kavach_patterns.

## Explicitly NOT done (per instructions)

- No integration into the live corpus or parliament.
- No fine-tuning code, no embeddings generated.
- No recommendations — counts only, for review before any decision.
